"""
LangGraph nodes for the Policy and Security Gate (Phase 6).

`authenticate_node` runs first and establishes who the user is.
`policy_gate_node` runs once a validated query plan exists and
decides whether that plan is allowed to run, and under what
row-level restrictions, column masking and resource limits.

Both nodes fail closed: any missing/invalid token, unrecognized
role, or policy-evaluation error results in `state["error"]` being
set so the graph routes to recovery instead of continuing.
"""

from agent.authentication import AuthenticationService
from agent.policy_engine import PolicyEngine
from agent.state import AgentState

_auth_service = AuthenticationService()
_policy_engine = PolicyEngine()


def authenticate_node(state: AgentState) -> AgentState:
    token = state.get("token")
    security_context = _auth_service.authenticate(token)

    if not security_context.authenticated:
        return {
            **state,
            "security_context": security_context.model_dump(),
            "error": "Authentication failed",
            "error_type": "authentication_error",
        }

    resolved_context = _policy_engine.build_security_context(security_context.user)

    return {
        **state,
        "security_context": resolved_context.model_dump(),
        "error": None,
        "error_type": None,
    }


def policy_gate_node(state: AgentState) -> AgentState:
    security_context_data = state.get("security_context")
    if not security_context_data:
        # Fail closed: no security context means no evaluation happened.
        return {
            **state,
            "error": "Policy evaluation unavailable: missing security context",
            "error_type": "policy_unavailable",
        }

    from agent.security_context import SecurityContext

    security_context = SecurityContext.model_validate(security_context_data)
    plan = state.get("query_plan") or {}

    decision = _policy_engine.evaluate(plan, security_context)

    if not decision.allowed:
        error_type = (
            "policy_unavailable"
            if (decision.reason or "").startswith("Policy evaluation unavailable")
            else "policy_denied"
        )
        return {
            **state,
            "policy_decision": decision.model_dump(),
            "error": decision.reason or "Access denied by policy",
            "error_type": error_type,
        }

    return {
        **state,
        "policy_decision": decision.model_dump(),
        "error": None,
        "error_type": None,
    }
