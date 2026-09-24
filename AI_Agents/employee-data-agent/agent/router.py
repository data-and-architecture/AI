def route_after_authentication(state):
    if state.get("error"):
        return "recovery"
    return "metadata"


def route_after_plan_validation(state):
    if state.get("error"):
        return "recovery"
    return "policy_gate"


def route_after_policy_gate(state):
    if state.get("error"):
        return "recovery"
    return "sql"


def route_after_sql_validation(state):
    if state.get("error"):
        return "recovery"
    return "database"


def route_after_database(state):
    if state.get("error"):
        return "recovery"
    return "verify_result"


def route_after_result_verification(state):
    if state.get("error"):
        return "recovery"
    return "interpret"


def route_after_recovery(state):
    return state.get("recovery_action", "answer")
