"""
LangChain tools that expose the governed YAML metadata (data
catalog, business glossary, semantic layer) to the LLM.

The metadata is the single source of truth. These tools let the
LLM *discover* approved metrics, dimensions, datasets and
relationships -- it can never invent one that isn't returned by
one of these tools.
"""

from typing import Any

from langchain_core.tools import tool

from agent.metadata_loader import MetadataLoader

metadata = MetadataLoader("metadata").load()


# ============================================================
# BUSINESS GLOSSARY
# ============================================================
@tool
def search_glossary(term: str) -> list[dict[str, Any]]:
    """
    Search the HR business glossary.

    Use this when the user uses natural business terminology.
    Examples: people, staff, team, department, salary, active employee.

    Returns canonical business definitions, resolving synonyms
    (e.g. "people" or "staff" both resolve to the "employee" term).
    
    Search the approved business glossary and resolve synonyms.

    """
    term = term.lower().strip()
    # First, search the glossary directly for the term.
    results = metadata.search_terms(term)

    # Then, resolve the term to its canonical form if it's a synonym.
    canonical = metadata.resolve_synonym(term)

    if canonical:
        canonical_term = metadata.get_term(canonical)
        if canonical_term and canonical_term not in results:
            results.append(canonical_term)  
    
    # Also check synonyms, so "people" resolves to "employee".
    #for canonical, synonyms in metadata.synonyms.items():
    #    if term in [s.lower() for s in synonyms]:
    #        canonical_term = metadata.get_term(canonical)
    #        if canonical_term and canonical_term not in results:
    #            results.append(canonical_term)

    # Return the final list of results, including any resolved canonical terms.
    return results


# ============================================================
# METRICS
# ============================================================
@tool
def search_metrics(query: str) -> list[dict[str, Any]]:
    """
    Search approved business metrics in the semantic layer.
    Never invent a metric. Examples: employee count, headcount,
    average salary, total salary.
    """
    return metadata.search_metrics(query)


@tool
def get_metric(metric_id: str) -> dict[str, Any] | None:
    """Retrieve one approved metric definition by its ID."""
    return metadata.get_metric(metric_id)


# ============================================================
# DIMENSIONS
# ============================================================
@tool
def search_dimensions(query: str) -> list[dict[str, Any]]:
    """
    Search approved semantic dimensions.
    Examples: department, team, location, job title, employment status.
    """
    return metadata.search_dimensions(query)


@tool
def get_dimension(dimension_id: str) -> dict[str, Any] | None:
    """Retrieve one approved dimension definition by its ID."""
    return metadata.get_dimension(dimension_id)


# ============================================================
# DATA CATALOG
# ============================================================
@tool
def search_datasets(query: str) -> list[dict[str, Any]]:
    """
    Search the data catalog for datasets.
    Examples: employees, department, employee data.
    """
    return metadata.search_datasets(query)


@tool
def get_dataset(dataset_id: str) -> dict[str, Any] | None:
    """Retrieve dataset metadata (physical table, schema, owner) by ID."""
    return metadata.get_dataset(dataset_id)


# ============================================================
# RELATIONSHIPS
# ============================================================
@tool
def search_relationships(query: str) -> list[dict[str, Any]]:
    """
    Search approved dataset relationships.
    Use this when determining how two datasets can be joined.
    """
    return metadata.search_relationships(query)


@tool
def get_relationship(relationship_id: str) -> dict[str, Any] | None:
    """Retrieve one approved dataset relationship (join) by ID."""
    return metadata.get_relationship(relationship_id)

@tool
def get_column(column_id: str) -> dict[str, Any] | None:
    """
    Retrieve one approved column from the data catalog.

    Example:
        employees.employee_id
        employees.salary
        departments.department_name
    """
    return metadata.get_column(column_id)

# ============================================================
# ALL METADATA TOOLS
# ============================================================
METADATA_TOOLS = [
    search_glossary,
    search_metrics,
    get_metric,
    search_dimensions,
    get_dimension,
    search_datasets,
    get_dataset,
    search_relationships,
    get_relationship,
    get_column,
]
