from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class MetadataAgentState(TypedDict):
    """State for the inner metadata-discovery tool-calling loop."""

    messages: Annotated[list[BaseMessage], add_messages]
