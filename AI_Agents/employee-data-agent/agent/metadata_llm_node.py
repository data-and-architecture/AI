from langchain_core.messages import SystemMessage

from agent.metadata_agent import SYSTEM_PROMPT, create_metadata_agent


def metadata_llm_node(state):
    llm = create_metadata_agent()
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm.invoke(messages)
    return {"messages": [response]}
