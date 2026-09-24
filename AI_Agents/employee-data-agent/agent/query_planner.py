import json

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from agent.query_plan import QueryPlan
from agent.state import AgentState

load_dotenv()

llm = ChatOpenAI(
    model="gpt-4.1-mini",
    temperature=0,
)

planner = llm.with_structured_output(QueryPlan)

PLANNER_PROMPT = """
You are an enterprise data query planner.

Create a QueryPlan using ONLY the VERIFIED metadata supplied below.

NEVER invent:
- metric IDs
- dimension IDs
- dataset IDs
- relationship IDs
- column IDs

Every selected object must exist in the verified metadata



Rules:

1. Metric must come from verified metrics.
2. Dimension must come from verified dimensions.
3. Dataset must come from verified datasets.
4. Relationship must come from verified relationships.
5. Columns must come from verified columns.
6. A metric may only use its allowed dimensions.
7. A join may only use an approved relationship.
8. Never create a join yourself.
9. If suitable metadata does not exist, request clarification.
10. Do not infer physical table names from the user question.

The MetadataContext is authoritative.
"""


def create_query_plan(
    question: str,
    metadata_context: dict,
    conversation_history: list[dict[str, str]] | None = None,
) -> QueryPlan:
    metadata_json = json.dumps(
        metadata_context,
        indent=2,
        default=str,
    )
    history_json = json.dumps((conversation_history or [])[-6:], default=str)
    prompt = f"""{PLANNER_PROMPT}

USER QUESTION:
{question}

RECENT CONVERSATION CONTEXT:
{history_json}

VERIFIED METADATA CONTEXT:
{metadata_json}
"""
    return planner.invoke(prompt)


def query_plan_node(state: AgentState) -> AgentState:
    """LangGraph node wrapper around create_query_plan."""
    plan = create_query_plan(
        state["question"],
        state.get("metadata_context", {}),
        state.get("conversation_history"),
    )
    plan_dict = plan.model_dump()
    plan_dict["request_id"] = state["request_id"]
    #print(f"Generated query plan: {json.dumps(plan_dict, indent=2)}")
    return {**state, "query_plan": plan_dict}
