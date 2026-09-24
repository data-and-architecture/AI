from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from agent.metadata_llm_node import metadata_llm_node
from agent.metadata_router import route_metadata_agent
from agent.metadata_state import MetadataAgentState
from agent.tool_node import execute_metadata_tools


def build_metadata_graph():
    graph = StateGraph(MetadataAgentState)

    # --------------------------------------------------------
    # Nodes
    # --------------------------------------------------------
    graph.add_node("llm", metadata_llm_node)
    graph.add_node("tools", execute_metadata_tools)

    # --------------------------------------------------------
    # Start
    # --------------------------------------------------------
    graph.add_edge(START, "llm")

    # --------------------------------------------------------
    # Conditional routing: keep looping while the LLM keeps
    # asking for metadata tools; stop once it settles.
    # --------------------------------------------------------
    graph.add_conditional_edges(
        "llm",
        route_metadata_agent,
        {
            "tools": "tools",
            "done": END,
        },
    )
    graph.add_edge("tools", "llm")

    return graph.compile()


def run_metadata_agent(question: str):
    graph = build_metadata_graph()
    return graph.invoke({"messages": [HumanMessage(content=question)]})
