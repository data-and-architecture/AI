from pydantic import BaseModel, Field


class MaskingRule(BaseModel):

    column_id: str

    strategy: str


class RowFilter(BaseModel):

    dataset_id: str

    column_id: str

    operator: str

    value: str


class ResourceLimits(BaseModel):

    max_rows: int = 10000

    max_scan_mb: int = 1024

    max_execution_seconds: int = 60


class PolicyDecision(BaseModel):

    allowed: bool = False

    reason: str | None = None

    row_filters: list[RowFilter] = Field(
        default_factory=list
    )

    masking_rules: list[MaskingRule] = Field(
        default_factory=list
    )

    limits: ResourceLimits = Field(
        default_factory=ResourceLimits
    )