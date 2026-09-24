from typing import Any
from pydantic import BaseModel, Field


class MetadataContext(BaseModel):
    """
    Verified metadata discovered for a single user question.

    This object is the trusted hand-off between:
        Metadata Discovery -> Query Planning
    """

    glossary_terms: list[dict[str, Any]] = Field(default_factory=list)
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    datasets: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    columns: list[dict[str, Any]] = Field(default_factory=list)


    discovery_status: str = "SUCCESS"
    discovery_errors: list[str] = Field(
        default_factory=list
    )

    def metric_ids(self) -> list[str]:
        return [
            item["id"]
            for item in self.metrics
            if "id" in item
        ]

    def dimension_ids(self) -> list[str]:
        return [
            item["id"]
            for item in self.dimensions
            if "id" in item
        ]

    def dataset_ids(self) -> list[str]:
        return [
            item["id"]
            for item in self.datasets
            if "id" in item
        ]

    def relationship_ids(self) -> list[str]:
        return [
            item["id"]
            for item in self.relationships
            if "id" in item
        ]

    def column_ids(self) -> list[str]:
        return [
            item["id"]
            for item in self.columns
            if "id" in item
        ]

    def glossary_ids(self) -> list[str]:
        return [
            item["id"]
            for item in self.glossary_terms
            if "id" in item
        ]
    
