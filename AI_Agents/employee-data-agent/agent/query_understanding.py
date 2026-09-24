from typing import Optional
from pydantic import BaseModel, Field

class FilterCondition(BaseModel):
    field: str
    operator: str
    value: str

class TimeRange(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None


class QueryUnderstanding(BaseModel):
    intent: str
    domain: str
    metric: Optional[str] = None
    dimensions: list[str] = Field(
        default_factory=list
    )
    filters: list[FilterCondition] = Field(
        default_factory=list
    )
    time_range: Optional[TimeRange] = None
    grain: Optional[str] = None
    security_sensitivity: str = "NORMAL"
    clarification_required: bool = False
    clarification_question: Optional[str] = None
    confidence: float = 0.0