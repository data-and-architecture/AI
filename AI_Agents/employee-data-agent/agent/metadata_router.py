MAX_METADATA_ITERATIONS = 6


def route_metadata_agent(state):
    messages = state["messages"]
    last_message = messages[-1]

    # Safety valve: never loop forever discovering metadata.
    tool_call_rounds = sum(
        1 for m in messages if getattr(m, "tool_calls", None)
    )
    if tool_call_rounds >= MAX_METADATA_ITERATIONS:
        return "done"

    if getattr(last_message, "tool_calls", None):
        return "tools"
    return "done"
