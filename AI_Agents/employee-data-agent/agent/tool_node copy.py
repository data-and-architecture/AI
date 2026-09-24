from langchain_core.messages import ToolMessage

from agent.tools import METADATA_TOOLS

TOOL_MAP = {tool.name: tool for tool in METADATA_TOOLS}


def execute_metadata_tools(state):
    messages = state["messages"]
    last_message = messages[-1]

    tool_messages = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool = TOOL_MAP.get(tool_name)

        if not tool:
            result = {"error": f"Unknown tool: {tool_name}"}
        else:
            result = tool.invoke(tool_args)

        tool_messages.append(
            ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"],
                name=tool_name,
            )
        )

    return {"messages": tool_messages}
