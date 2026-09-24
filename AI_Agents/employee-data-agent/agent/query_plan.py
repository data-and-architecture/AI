from typing import Literal, Optional

from pydantic import BaseModel, Field


class QueryPlanFilter(BaseModel):
    column: str
    operator: Literal[
        "equals",
        "not_equals",
        "greater_than",
        "less_than",
        "greater_than_or_equal",
        "less_than_or_equal",
        "in",
        "not_in",
    ]
    value: str


class QueryPlanTimeRange(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None


class QueryPlanSort(BaseModel):
    column: str
    direction: Literal["asc", "desc"] = "asc"


class QueryPlan(BaseModel):

    #request_id: str
    domain: str

    metric: str = Field(description="Approved semantic metric ID.")

    dimensions: list[str] = Field(
        default_factory=list,
        description="Approved semantic dimension IDs.",
    )
    datasets: list[str] = Field(
        default_factory=list,
        description="Required catalog dataset IDs.",
    )
    relationships: list[str] = Field(
        default_factory=list,
        description="Approved relationship IDs.",
    )

    filters: list[QueryPlanFilter] = Field(
        default_factory=list
    )

    time_range: Optional[ QueryPlanTimeRange  ] = None 

    sort: list[QueryPlanSort] = Field(
        default_factory=list
    )

    limit: int = 1000

    grain: Optional[str] = None

    confidence: float = 0.0

    clarification_required: bool = False

    clarification_question: Optional[str] = None

    