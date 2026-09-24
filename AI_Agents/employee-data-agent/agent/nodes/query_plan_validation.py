from agent.query_plan import QueryPlan
from agent.query_plan_validator import (
    QueryPlanValidator,
    QueryPlanValidationError,
)

def query_plan_validation_node(state):

    plan = QueryPlan.model_validate(
        state["query_plan"]
    )

    validator = QueryPlanValidator(
        metadata=None
    )

    context = state[
        "metadata_context"
    ]

    validated_plan = validator.validate(
        plan,
        context
    )

    return {
        **state,

        "query_plan":
            validated_plan.model_dump(),

        "query_plan_valid":
            True,

        "error": None
    }

