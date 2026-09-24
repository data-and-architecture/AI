import json

from langchain_openai import ChatOpenAI

from agent.query_understanding import QueryUnderstanding


llm = ChatOpenAI(
    model="gpt-4.1-mini",
    temperature=0,
)

understanding_llm = llm.with_structured_output(
    QueryUnderstanding
)


def query_understanding_node(state):

    question = state["question"]

    metadata_context = state.get(
        "metadata_context",
        {}
    )

    prompt = f"""
You are a Query Understanding Agent.

Do not generate SQL.

Interpret the business meaning of the question.

Use ONLY the verified metadata.

QUESTION:
{question}

VERIFIED METADATA:
{json.dumps(
    metadata_context,
    indent=2,
    default=str
)}
"""

    understanding = understanding_llm.invoke(
        prompt
    )

    return {
        **state,
        "query_understanding":
            understanding.model_dump()
    }