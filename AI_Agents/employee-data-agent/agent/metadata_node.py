"""
Wraps the inner metadata tool-calling subgraph (agent/metadata_graph.py)
as a single node in the main AgentState graph.

It runs the LLM + tool-calling loop, then reduces the resulting
message history into a plain-text "metadata_context" digest that
the query planner (agent/query_planner.py) uses as grounding --
this is the only thing the planner is allowed to build a QueryPlan
from, which is what stops it inventing metric/dimension/dataset ids.
"""
import json

from langchain_core import messages
from langchain_core.messages import AIMessage, ToolMessage
from opentelemetry import context
from sqlalchemy import Null

from agent.metadata_graph import build_metadata_graph
from agent.metadata_context import MetadataContext
from agent.state import AgentState

# Helper function to parse the result from a ToolMessage. Returns the parsed JSON if possible, otherwise None.
def _parse_tool_result(message: ToolMessage):
    content = message.content
    if isinstance(content, str):
        try:
            return json.loads(content)
            #return json.dumps(content)
        except json.JSONDecodeError:
            #print(f"Failed to parse tool result: {content}")
            return None
    return content

# Helper function to append items to a list, ensuring uniqueness based on the "id" field.
def _append_unique(target: list, items):
    if items is None:
        return
    if not isinstance(items, list):
        items = [items]
    existing_ids = {
        item.get("id")
        for item in target
        if isinstance(item, dict) and item.get("id")
    }
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if item_id and item_id not in existing_ids:
            target.append(item)
            existing_ids.add(item_id)
     

def build_metadata_context(messages) -> MetadataContext:
    context = MetadataContext()
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        result = _parse_tool_result(message)
        if message.name == "search_glossary":
            _append_unique(
                context.glossary_terms,
                result,
            )
        elif message.name == "search_metrics":
            _append_unique(
                context.metrics,
                result,
            )
        elif message.name == "get_metric":
            _append_unique(
                context.metrics,
                result,
            )
        elif message.name == "search_dimensions":
            _append_unique(
                context.dimensions,
                result,
            )
        elif message.name == "get_dimension":
            _append_unique(
                context.dimensions,
                result,
            )
        elif message.name == "search_datasets":
            _append_unique(
                context.datasets,
                result,
            )
        elif message.name == "get_dataset":
            _append_unique(
                context.datasets,
                result,
            )
        elif message.name == "search_relationships":
            _append_unique(
                context.relationships,
                result,
            )
        elif message.name == "get_relationship":
            _append_unique(
                context.relationships,
                result,
            )
        elif message.name == "get_column":
            _append_unique(
                context.columns,
                result,
            )            
    return context



def metadata_agent_node(state: AgentState) -> AgentState:


    graph = build_metadata_graph()

    from langchain_core.messages import HumanMessage

    result = graph.invoke({"messages": [HumanMessage(content=state["question"])]})
    messages = result["messages"]
  
    #print(messages)

    
    #context_lines = []
    #for message in messages:
    #    if isinstance(message, ToolMessage):
    #        context_lines.append(f"[{message.name}] -> {message.content}")
    #    elif isinstance(message, AIMessage) and message.content:
    #        context_lines.append(f"[agent] {message.content}")

    #metadata_context = "\n".join(context_lines) if context_lines else (
    #    "No metadata was discovered for this question."
    #)
    
    metadata_context = build_metadata_context(messages)



   # return {
   #     **state,
   #     "metadata_context": metadata_context,
   # }

    return {
        **state,

        "metadata_context": metadata_context.model_dump(),

        "glossary_terms": metadata_context.glossary_terms,
        "metrics": metadata_context.metrics,
        "dimensions": metadata_context.dimensions,
        "datasets": metadata_context.datasets,
        "relationships": metadata_context.relationships,
        "columns": metadata_context.columns,
    }
