from pathlib import Path
from typing import Any

import yaml


class MetadataLoader:
    """
    Loads Data Catalog, Business Glossary and Semantic Layer
    metadata from YAML files.

    YAML is the source of truth for metadata; PostgreSQL (or
    whichever database is configured) is the source of truth
    for actual data.
    """

    def __init__(self, metadata_path: str = "metadata"):
        self.base_path = Path(metadata_path)
        self.catalog_path = self.base_path / "catalog"
        self.glossary_path = self.base_path / "glossary"
        self.semantic_path = self.base_path / "semantic"

        self.datasets: dict[str, Any] = {}
        self.columns: dict[str, Any] = {}
        self.terms: dict[str, Any] = {}
        self.synonyms: dict[str, Any] = {}
        self.metrics: dict[str, Any] = {}
        self.dimensions: dict[str, Any] = {}
        self.relationships: dict[str, Any] = {}
        self.version = "unknown"

    # ---------------------------------------------------------
    # YAML
    # ---------------------------------------------------------
    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"Metadata file not found: {path}")
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
        return data or {}

    # ---------------------------------------------------------
    # Load all metadata
    # ---------------------------------------------------------
    def load(self) -> "MetadataLoader":
        self._load_catalog()
        self._load_glossary()
        self._load_semantic_layer()
        return self

    # ---------------------------------------------------------
    # Catalog
    # ---------------------------------------------------------
    def _load_catalog(self):
        datasets_data = self._load_yaml(self.catalog_path / "datasets.yaml")
        columns_data = self._load_yaml(self.catalog_path / "columns.yaml")
        self.version = str(datasets_data.get("version", "unknown"))

        for dataset in datasets_data.get("datasets", []):          
            self.datasets[dataset["id"]] = dataset
        for column in columns_data.get("columns", []):
            self.columns[column["id"]] = column
    

    # ---------------------------------------------------------
    # Glossary
    # ---------------------------------------------------------
    def _load_glossary(self):
        terms_data = self._load_yaml(self.glossary_path / "terms.yaml")
        synonyms_data = self._load_yaml(self.glossary_path / "synonyms.yaml")

        for term in terms_data.get("terms", []):
            self.terms[term["id"]] = term
        for synonym in synonyms_data.get("synonyms", []):
            canonical = synonym["canonical_term"]
            self.synonyms[canonical] = synonym["values"]

    # ---------------------------------------------------------
    # Synonym Resolution
    # ---------------------------------------------------------
    def resolve_synonym(self, value: str) -> str | None:
        value = value.lower().strip()

        for canonical, synonyms in self.synonyms.items():
            if value == canonical.lower():
                return canonical

            if value in [s.lower() for s in synonyms]:
                return canonical

        return None


    def _expand_search_terms(self, query: str) -> set[str]:
        """All strings worth substring-matching against, given a raw
        search query.

        search_glossary already resolves synonyms via resolve_synonym,
        but search_metrics/search_dimensions/search_datasets/
        search_relationships previously did a bare substring match on
        id/name/description with no synonym awareness at all -- so a
        user saying "team" (a documented synonym of "department") or
        "headcount"/"pay" would get zero results from those tools even
        though the concept is approved, which surfaces to the user as
        a false "ambiguous_term" clarification request instead of a
        found answer. This expands a query word-by-word to every
        synonym-group member so id/name/description matching sees the
        same vocabulary search_glossary already sees.
        """
        query = query.lower().strip()
        expanded = {query}
        # Whole query, then each individual word, in case the caller
        # passes a short phrase rather than a single term.
        for candidate in [query, *query.split()]:
            canonical = self.resolve_synonym(candidate)
            if canonical:
                expanded.add(canonical.lower())
                expanded.update(value.lower() for value in self.synonyms.get(canonical, []))
        return expanded


    @staticmethod
    def _matches_any(searchable: str, terms: set[str]) -> bool:
        return any(term in searchable for term in terms)


    # ---------------------------------------------------------
    # Semantic Layer
    # ---------------------------------------------------------
    def _load_semantic_layer(self):
        metrics_data = self._load_yaml(self.semantic_path / "metrics.yaml")
        dimensions_data = self._load_yaml(self.semantic_path / "dimensions.yaml")
        relationships_data = self._load_yaml(
            self.semantic_path / "relationships.yaml"
        )

        for metric in metrics_data.get("metrics", []):
            self.metrics[metric["id"]] = metric
        for dimension in dimensions_data.get("dimensions", []):
            self.dimensions[dimension["id"]] = dimension
        for relationship in relationships_data.get("relationships", []):
            self.relationships[relationship["id"]] = relationship

    # ---------------------------------------------------------
    # Catalog API
    # ---------------------------------------------------------
    def get_dataset(self, dataset_id: str):
        return self.datasets.get(dataset_id)

    def get_column(self, column_id: str):
        return self.columns.get(column_id)

    # ---------------------------------------------------------
    # Glossary API
    # ---------------------------------------------------------
    def get_term(self, term_id: str):
        return self.terms.get(term_id)

    def get_synonyms(self, term_id: str):
        return self.synonyms.get(term_id, [])

    # ---------------------------------------------------------
    # Semantic API
    # ---------------------------------------------------------
    def get_metric(self, metric_id: str):
        return self.metrics.get(metric_id)

    def get_dimension(self, dimension_id: str):
        return self.dimensions.get(dimension_id)

    def get_relationship(self, relationship_id: str):
        return self.relationships.get(relationship_id)

    # ---------------------------------------------------------
    # Search
    # ---------------------------------------------------------
    def search_terms(self, query: str):
        terms = self._expand_search_terms(query)
        results = []
        for term in self.terms.values():
            searchable = f"{term['id']} {term.get('name', '')} {term.get('definition', '')}".lower()
            if self._matches_any(searchable, terms):
                results.append(term)
        return results

    def search_metrics(self, query: str):
        terms = self._expand_search_terms(query)
        results = []
        for metric in self.metrics.values():
            searchable = f"{metric['id']} {metric.get('name', '')} {metric.get('description', '')}".lower()
            if self._matches_any(searchable, terms):
                results.append(metric)
        return results

    def search_dimensions(self, query: str):
        terms = self._expand_search_terms(query)
        results = []
        for dimension in self.dimensions.values():
            searchable = (
                f"{dimension['id']} {dimension.get('name', '')} "
                f"{dimension.get('description', '')}"
            ).lower()
            if self._matches_any(searchable, terms):
                results.append(dimension)
        return results

    def search_datasets(self, query: str):
        terms = self._expand_search_terms(query)
        results = []
        for dataset in self.datasets.values():
            searchable = " ".join(
                [
                    dataset.get("id", ""),
                    dataset.get("name", ""),
                    dataset.get("description", ""),
                ]
            ).lower()
            if self._matches_any(searchable, terms):
                results.append(dataset)
        return results

    def search_relationships(self, query: str):
        terms = self._expand_search_terms(query)
        results = []
        for relationship in self.relationships.values():
            searchable = " ".join(
                [
                    relationship.get("id", ""),
                    relationship.get("name", ""),
                    relationship.get("description", ""),
                ]
            ).lower()
            if self._matches_any(searchable, terms):
                results.append(relationship)
        return results

    # ---------------------------------------------------------
    # Debug
    # ---------------------------------------------------------
    def summary(self):
        return {
            "datasets": len(self.datasets),
            "columns": len(self.columns),
            "terms": len(self.terms),
            "synonym_groups": len(self.synonyms),
            "metrics": len(self.metrics),
            "dimensions": len(self.dimensions),
            "relationships": len(self.relationships),
        }


if __name__ == "__main__":
    loader = MetadataLoader("metadata")
    loader.load()
    print("\nMetadata loaded successfully.")
    print(loader.summary())


    print("\nMetrics:")
    for metric_id, metric in loader.metrics.items():
        print(f"- {metric_id}: {metric['name']}")

    print("\nDimensions:")
    for dimension_id, dimension in loader.dimensions.items():
        print(f"- {dimension_id}: {dimension['name']}")

    print("\nRelationships:")
    for relationship_id, relationship in loader.relationships.items():
        print(f"- {relationship_id}: {relationship['name']}")

    print("\nColumns:")
    for column_id, column in loader.columns.items():
        print(f"- {column_id}: {column['name']}")               

    print("\nTerms:")
    for term_id, term in loader.terms.items():
        print(f"- {term_id}: {term['name']}")   

 

