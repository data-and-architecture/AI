from langgraph.graph import END, START, StateGraph

from agent.answer_generator import generate_answer
from agent.audit import audit_node, audit_start_node
from agent.database import execute_sql
from agent.metadata_node import metadata_agent_node
from agent.observability import instrument_node
from agent.policy_node import authenticate_node, policy_gate_node
from agent.query_planner import query_plan_node
from agent.recovery import recovery_node
from agent.result_interpreter import interpret_result
from agent.result_verifier import verify_result
from agent.router import (
    route_after_authentication,
    route_after_database,
    route_after_plan_validation,
    route_after_policy_gate,
    route_after_recovery,
    route_after_result_verification,
    route_after_sql_validation,
)
from agent.sql_generator import generate_sql
from agent.state import AgentState
from agent.validators import validate_query_plan, validate_sql


def build_graph():
    graph = StateGraph(AgentState)

    # ========================================================
    # Nodes
    # ========================================================
    graph.add_node("audit_start", instrument_node("audit_start", audit_start_node))
    graph.add_node("authenticate", instrument_node("authenticate", authenticate_node))
    graph.add_node("metadata", instrument_node("metadata", metadata_agent_node))
    graph.add_node("query_plan", instrument_node("query_plan", query_plan_node))
    graph.add_node("validate_plan", instrument_node("validate_plan", validate_query_plan))
    graph.add_node("policy_gate", instrument_node("policy_gate", policy_gate_node))
    graph.add_node("sql", instrument_node("sql", generate_sql))
    graph.add_node("validate_sql", instrument_node("validate_sql", validate_sql))
    graph.add_node("database", instrument_node("database", execute_sql))
    graph.add_node("verify_result", instrument_node("verify_result", verify_result))
    graph.add_node("interpret", instrument_node("interpret", interpret_result))
    graph.add_node("answer", instrument_node("answer", generate_answer))
    graph.add_node("audit", instrument_node("audit", audit_node))
    graph.add_node("recovery", instrument_node("recovery", recovery_node))

    # ========================================================
    # Main flow
    # ========================================================
    graph.add_edge(START, "audit_start")
    graph.add_edge("audit_start", "authenticate")
    graph.add_conditional_edges(
        "authenticate",
        route_after_authentication,
        {"metadata": "metadata", "recovery": "recovery"},
    )
    graph.add_edge("metadata", "query_plan")
    graph.add_edge("query_plan", "validate_plan")

    # ========================================================
    # Query-plan validation
    # ========================================================
    graph.add_conditional_edges(
        "validate_plan",
        route_after_plan_validation,
        {"policy_gate": "policy_gate", "recovery": "recovery"},
    )

    # ========================================================
    # Policy and Security Gate
    # ========================================================
    graph.add_conditional_edges(
        "policy_gate",
        route_after_policy_gate,
        {"sql": "sql", "recovery": "recovery"},
    )

    # ========================================================
    # SQL
    # ========================================================
    graph.add_edge("sql", "validate_sql")
    graph.add_conditional_edges(
        "validate_sql",
        route_after_sql_validation,
        {"database": "database", "recovery": "recovery"},
    )

    # ========================================================
    # Database
    # ========================================================
    graph.add_conditional_edges(
        "database",
        route_after_database,
        {"verify_result": "verify_result", "recovery": "recovery"},
    )
    graph.add_conditional_edges(
        "verify_result",
        route_after_result_verification,
        {"interpret": "interpret", "recovery": "recovery"},
    )

    # ========================================================
    # Result
    # ========================================================
    graph.add_edge("interpret", "answer")
    graph.add_edge("answer", "audit")
    graph.add_edge("audit", END)

    # ========================================================
    # Recovery
    # ========================================================
    graph.add_conditional_edges(
        "recovery",
        route_after_recovery,
        {
            "retry_metadata": "metadata",
            "retry_database": "database",
            "answer": "answer",
        },
    )

    return graph.compile()
