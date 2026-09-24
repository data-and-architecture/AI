import asyncio
import os
from collections import defaultdict, deque
from pathlib import Path
from threading import Event, Lock
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent.audit import recent_audit_events
from agent.authentication import AuthenticationService
from agent.graph import build_graph
from agent.knowledge_graph import build_knowledge_graph
from agent.metadata_loader import MetadataLoader
from agent.observability import prometheus_metrics
from agent.policy_engine import PolicyEngine
from agent.security_context import SecurityContext

MAX_REQUEST_BYTES = int(os.getenv("API_MAX_REQUEST_BYTES", "16384"))
MAX_QUESTION_CHARS = int(os.getenv("API_MAX_QUESTION_CHARS", "4000"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("API_REQUEST_TIMEOUT_SECONDS", "30"))
RATE_LIMIT_REQUESTS = int(os.getenv("API_RATE_LIMIT_REQUESTS", "30"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("API_RATE_LIMIT_WINDOW_SECONDS", "60"))
MAX_SESSION_MESSAGES = 12
STATIC_INDEX = Path(__file__).parent / "static" / "index.html"


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    session_id: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)


class ChatResponse(BaseModel):
    answer: str
    result: list[dict[str, Any]]
    request_id: str
    correlation_id: str
    session_id: str
    explanation: dict[str, Any]
    authorized_sql: str | None = None


class InMemoryApiStore:

    def __init__(self):
        self._lock = Lock()
        self._sessions: dict[tuple[str, str], deque[dict[str, str]]] = defaultdict(
            lambda: deque(maxlen=MAX_SESSION_MESSAGES)
        )
        self._rate_windows: dict[str, deque[float]] = defaultdict(deque)
        self._active_requests: dict[str, Event] = {}

    def check_rate_limit(self, user_id: str) -> None:
        now = monotonic()
        with self._lock:
            window = self._rate_windows[user_id]
            while window and now - window[0] >= RATE_LIMIT_WINDOW_SECONDS:
                window.popleft()
            if len(window) >= RATE_LIMIT_REQUESTS:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again shortly.",
                )
            window.append(now)

    def history(self, user_id: str, session_id: str) -> list[dict[str, str]]:
        with self._lock:
            return list(self._sessions[(user_id, session_id)])

    def append(self, user_id: str, session_id: str, role: str, content: str) -> None:
        with self._lock:
            self._sessions[(user_id, session_id)].append({"role": role, "content": content})

    def register(self, request_id: str, cancellation_event: Event) -> None:
        with self._lock:
            self._active_requests[request_id] = cancellation_event

    def complete(self, request_id: str) -> None:
        with self._lock:
            self._active_requests.pop(request_id, None)

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            cancellation_event = self._active_requests.get(request_id)
        if not cancellation_event:
            return False
        cancellation_event.set()
        return True


def _token_from_header(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A Bearer token is required.",
        )
    return authorization.removeprefix("Bearer ").strip()


def _resolve_security_context(token: str) -> SecurityContext:
    identity_context = AuthenticationService().authenticate(token)
    if not identity_context.authenticated or not identity_context.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed.",
        )
    security_context = PolicyEngine().build_security_context(identity_context.user)
    if not security_context.user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No authorized identity was resolved.",
        )
    return security_context


def _explanation(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "failed" if result.get("error") else "verified",
        "summary": result.get("result_summary"),
        "result_verification": result.get("result_verification"),
        "error_type": result.get("error_type"),
    }


def create_app(graph_factory: Callable[[], Any] = build_graph) -> FastAPI:
    app = FastAPI(title="Employee Data Agent API", version="1.0")
    app.state.store = InMemoryApiStore()
    app.state.graph_factory = graph_factory
    app.state.graph = None

    def graph():
        if app.state.graph is None:
            app.state.graph = app.state.graph_factory()
        return app.state.graph

    @app.middleware("http")
    async def enforce_request_size(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BYTES:
            return Response("Request body is too large.", status_code=413)
        body = await request.body()
        if len(body) > MAX_REQUEST_BYTES:
            return Response("Request body is too large.", status_code=413)
        return await call_next(request)

    @app.get("/", include_in_schema=False)
    async def ui():
        return FileResponse(STATIC_INDEX)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return Response(prometheus_metrics(), media_type="text/plain; version=0.0.4")

    @app.post("/chat", response_model=ChatResponse)
    async def chat(payload: ChatRequest, authorization: str | None = Header(default=None)):
        token = _token_from_header(authorization)
        security_context = _resolve_security_context(token)
        user_id = security_context.user.user_id
        app.state.store.check_rate_limit(user_id)

        session_id = payload.session_id or str(uuid4())
        request_id = payload.request_id or str(uuid4())
        cancellation_event = Event()
        history = app.state.store.history(user_id, session_id)
        initial_state = {
            "question": payload.question,
            "token": token,
            "request_id": request_id,
            "correlation_id": request_id,
            "retry_count": 0,
            "conversation_history": history,
            "cancellation_event": cancellation_event,
        }
        app.state.store.register(request_id, cancellation_event)
        invocation = asyncio.create_task(asyncio.to_thread(graph().invoke, initial_state))
        try:
            result = await asyncio.wait_for(asyncio.shield(invocation), REQUEST_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            cancellation_event.set()
            invocation.add_done_callback(lambda _: app.state.store.complete(request_id))
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="The request exceeded the configured timeout.",
            )
        finally:
            if invocation.done():
                app.state.store.complete(request_id)

        if cancellation_event.is_set() or result.get("error_type") == "cancelled":
            raise HTTPException(status_code=499, detail="The request was cancelled.")

        answer = result.get("answer", "I couldn't safely answer that request.")
        app.state.store.append(user_id, session_id, "user", payload.question)
        app.state.store.append(user_id, session_id, "assistant", answer)
        authorized_sql = result.get("sql") if security_context.can_view_sql else None
        return ChatResponse(
            answer=answer,
            result=result.get("result", []),
            request_id=result.get("request_id", request_id),
            correlation_id=result.get("correlation_id", request_id),
            session_id=session_id,
            explanation=_explanation(result),
            authorized_sql=authorized_sql,
        )

    @app.post("/chat/{request_id}/cancel")
    async def cancel_chat(request_id: str, authorization: str | None = Header(default=None)):
        _resolve_security_context(_token_from_header(authorization))
        if not app.state.store.cancel(request_id):
            raise HTTPException(status_code=404, detail="No active request was found.")
        return {"request_id": request_id, "status": "cancellation_requested"}

    @app.get("/sessions/{session_id}")
    async def session_history(session_id: str, authorization: str | None = Header(default=None)):
        security_context = _resolve_security_context(_token_from_header(authorization))
        return {
            "session_id": session_id,
            "messages": app.state.store.history(security_context.user.user_id, session_id),
        }

    def require_admin(authorization: str | None) -> SecurityContext:
        security_context = _resolve_security_context(_token_from_header(authorization))
        if not security_context.can_view_admin:
            raise HTTPException(status_code=403, detail="Administrative access is required.")
        return security_context

    @app.get("/admin/metadata")
    async def admin_metadata(authorization: str | None = Header(default=None)):
        require_admin(authorization)
        metadata = MetadataLoader("metadata").load()
        graph_snapshot = build_knowledge_graph().to_dict()
        return {
            "version": metadata.version,
            "datasets": len(metadata.datasets),
            "columns": len(metadata.columns),
            "metrics": len(metadata.metrics),
            "dimensions": len(metadata.dimensions),
            "relationships": len(metadata.relationships),
            "knowledge_graph": {
                "nodes": len(graph_snapshot["nodes"]),
                "edges": len(graph_snapshot["edges"]),
            },
        }

    @app.get("/admin/audit")
    async def admin_audit(
        limit: int = 50, authorization: str | None = Header(default=None)
    ):
        require_admin(authorization)
        return {"events": recent_audit_events(limit)}

    return app


app = create_app()
