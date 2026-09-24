from agent.state import AgentState


def interpret_result(state: AgentState) -> AgentState:
    result = state.get("result", [])

    if state.get("error"):
        return {
            **state,
            "result_summary": f"Database execution failed: {state['error']}",
        }

    if not result:
        return {**state, "result_summary": "The query returned no rows."}

    row_count = len(result)
    return {**state, "result_summary": f"The query returned {row_count} rows."}
