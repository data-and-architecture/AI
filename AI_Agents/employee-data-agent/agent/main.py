from agent.graph import build_graph
from agent.security_context import SecurityContext
import json


def main():
    graph = build_graph()
    question = input("\nAsk a question: ")

    # Prototype only: a real deployment would source this from the
    # incoming request's Authorization header (Okta / Entra ID / etc.).
    token = "demo-token"

    initial_state = {"question": question, "token": token, "retry_count": 0}
    result = graph.invoke(initial_state)

    print("\n==============================")
    print("Answer")
    print("==============================")
    print(result.get("answer", "No answer generated."))

    security_context = result.get("security_context")
    if security_context and SecurityContext.model_validate(security_context).can_view_sql:
        print("\n==============================")
        print("SQL")
        print("==============================")
        print(result.get("sql", "No SQL generated."))

    if result.get("sql_compilation"):
        print("\n==============================")
        print("SQL Compilation Metadata")
        print("==============================")
        print(json.dumps(result["sql_compilation"], indent=2, default=str))

    if result.get("error"):
        print("\n==============================")
        print("Error")
        print("==============================")
        print(result["error"])


if __name__ == "__main__":
    main()
