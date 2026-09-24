from agent.connection_registry import ConnectionRegistry
from agent.metadata_loader import MetadataLoader
from agent.query_executor import ExecutionLimits, QueryExecutor
from agent.state import AgentState
from time import perf_counter

metadata = MetadataLoader("metadata").load()
registry = ConnectionRegistry().load()


def resolve_executor(state: AgentState) -> tuple[QueryExecutor, ExecutionLimits]:
    policy_decision = state.get("policy_decision")
    compilation = state.get("sql_compilation")
    if not compilation or not policy_decision or not policy_decision.get("allowed"):
        raise PermissionError("Policy evaluation unavailable: execution blocked")

    limits = policy_decision.get("limits", {})
    execution_limits = ExecutionLimits(
        max_rows=int(limits["max_rows"]),
        max_scan_mb=int(limits["max_scan_mb"]),
        max_execution_seconds=int(limits["max_execution_seconds"]),
    )
    base_dataset = metadata.get_dataset(compilation["base_dataset"])
    if not base_dataset:
        raise PermissionError("Compiled base dataset is not in the catalog")

    database = base_dataset["database"]
    connection_id = database.get("connection")
    if not connection_id:
        raise PermissionError("Catalog dataset has no registered connection ID")

    for dataset_id in state.get("query_plan", {}).get("datasets", []):
        dataset = metadata.get_dataset(dataset_id)
        if not dataset or dataset["database"].get("connection") != connection_id:
            raise PermissionError("Queries cannot span registered connections")

    #print(f"Resolved executor for connection {connection_id} and database {database['name']}")

    return registry.executor_for(connection_id, database["name"]), execution_limits


def execute_sql(state: AgentState) -> AgentState:
    sql = state.get("sql")
    if not sql:
        return {
            **state,
            "result": [],
            "error": "No SQL was generated",
            "error_type": "database_error",
        }

    started = perf_counter()
    try:
        executor, execution_limits = resolve_executor(state)
        execution = executor.execute(
            sql,
            state.get("sql_parameters", {}),
            execution_limits,
        )
        return {
            **state,
            "result": execution.rows,
            "execution_duration_ms": round((perf_counter() - started) * 1000, 3),
            "error": None,
            "error_type": None,
        }
    except Exception as exc:
        message = str(exc)
        error_type = (
            "database_timeout"
            if isinstance(exc, TimeoutError) or "timeout" in message.lower()
            else "database_error"
        )
        print(f"SQL execution failed: {message} (type: {error_type})")
        return {
            **state,
            "result": [],
            "execution_duration_ms": round((perf_counter() - started) * 1000, 3),
            "error": message,
            "error_type": error_type,
        }
