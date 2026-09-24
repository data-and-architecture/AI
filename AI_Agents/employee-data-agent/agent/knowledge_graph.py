import json
from dataclasses import dataclass, field
from typing import Any

from agent.metadata_loader import MetadataLoader
from agent.policy_loader import PolicyLoader

NODE_TYPES = {
    "Domain",
    "Dataset",
    "Column",
    "GlossaryTerm",
    "Metric",
    "Dimension",
    "Relationship",
    "Policy",
    "Owner",
}
EDGE_TYPES = {
    "DEFINES",
    "SYNONYM_OF",
    "USES_DATASET",
    "USES_COLUMN",
    "ALLOWED_DIMENSION",
    "JOINS_TO",
    "OWNED_BY",
    "PROTECTED_BY",
}


@dataclass(frozen=True)
class KnowledgeGraphNode:
    node_id: str
    node_type: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeGraphEdge:
    source_id: str
    edge_type: str
    target_id: str
    properties: dict[str, Any] = field(default_factory=dict)


class KnowledgeGraph:
    """Small, deterministic graph projected only from approved metadata."""

    def __init__(self):
        self.nodes: dict[str, KnowledgeGraphNode] = {}
        self.edges: list[KnowledgeGraphEdge] = []
        self._edge_keys: set[tuple[str, str, str, str]] = set()

    def add_node(
        self, node_id: str, node_type: str, properties: dict[str, Any] | None = None
    ) -> None:
        if node_type not in NODE_TYPES:
            raise ValueError(f"Unsupported knowledge graph node type: {node_type}")
        node = KnowledgeGraphNode(node_id, node_type, properties or {})
        existing = self.nodes.get(node_id)
        if existing and existing != node:
            raise ValueError(f"Conflicting knowledge graph node: {node_id}")
        self.nodes[node_id] = node

    def add_edge(
        self,
        source_id: str,
        edge_type: str,
        target_id: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"Unsupported knowledge graph edge type: {edge_type}")
        if source_id not in self.nodes or target_id not in self.nodes:
            raise ValueError("Knowledge graph edges require existing nodes")
        edge_properties = properties or {}
        key = (
            source_id,
            edge_type,
            target_id,
            json.dumps(edge_properties, sort_keys=True, default=str),
        )
        if key in self._edge_keys:
            return
        self._edge_keys.add(key)
        self.edges.append(
            KnowledgeGraphEdge(source_id, edge_type, target_id, edge_properties)
        )

    def edges_of_type(self, edge_type: str) -> list[KnowledgeGraphEdge]:
        return [edge for edge in self.edges if edge.edge_type == edge_type]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "id": node.node_id,
                    "type": node.node_type,
                    "properties": node.properties,
                }
                for node in self.nodes.values()
            ],
            "edges": [
                {
                    "source": edge.source_id,
                    "type": edge.edge_type,
                    "target": edge.target_id,
                    "properties": edge.properties,
                }
                for edge in self.edges
            ],
        }


def _node_id(node_type: str, value: str) -> str:
    return f"{node_type.lower()}:{value}"


def _dataset_column_id(dataset_id: str, column_name: str) -> str:
    return _node_id("Column", f"{dataset_id}.{column_name}")


def _add_domain_edge(graph: KnowledgeGraph, domain_id: str, target_id: str) -> None:
    graph.add_edge(domain_id, "DEFINES", target_id)


def build_knowledge_graph(
    metadata_path: str = "metadata", policy_path: str = "config/security.yaml"
) -> KnowledgeGraph:
    metadata = MetadataLoader(metadata_path).load()
    policies = PolicyLoader(policy_path).load()
    graph = KnowledgeGraph()

    domain_names = {dataset["domain"] for dataset in metadata.datasets.values()}
    for domain_name in domain_names:
        graph.add_node(
            _node_id("Domain", domain_name),
            "Domain",
            {"name": domain_name},
        )

    for dataset_id, dataset in metadata.datasets.items():
        domain_id = _node_id("Domain", dataset["domain"])
        dataset_node_id = _node_id("Dataset", dataset_id)
        graph.add_node(
            dataset_node_id,
            "Dataset",
            {
                "name": dataset["name"],
                "database": dataset["database"]["name"],
                "schema": dataset["database"]["schema"],
                "table": dataset["database"]["table"],
            },
        )
        _add_domain_edge(graph, domain_id, dataset_node_id)

        owner_name = dataset.get("owner", {}).get("team")
        if owner_name:
            owner_id = _node_id("Owner", owner_name)
            graph.add_node(owner_id, "Owner", {"name": owner_name})
            graph.add_edge(dataset_node_id, "OWNED_BY", owner_id)

    for column_id, column in metadata.columns.items():
        dataset_node_id = _node_id("Dataset", column["dataset"])
        column_node_id = _node_id("Column", column_id)
        dataset = metadata.get_dataset(column["dataset"])
        graph.add_node(
            column_node_id,
            "Column",
            {
                "name": column["name"],
                "data_type": column["data_type"],
                "classification": column.get("classification", "unknown"),
            },
        )
        graph.add_edge(dataset_node_id, "DEFINES", column_node_id)
        _add_domain_edge(graph, _node_id("Domain", dataset["domain"]), column_node_id)

    for term_id, term in metadata.terms.items():
        domain_id = _node_id("Domain", term["domain"])
        term_node_id = _node_id("GlossaryTerm", term_id)
        graph.add_node(
            term_node_id,
            "GlossaryTerm",
            {"name": term["name"], "approved": term.get("status") == "approved"},
        )
        _add_domain_edge(graph, domain_id, term_node_id)

    for canonical, synonyms in metadata.synonyms.items():
        canonical_id = _node_id("GlossaryTerm", canonical)
        if canonical_id not in graph.nodes:
            graph.add_node(canonical_id, "GlossaryTerm", {"name": canonical, "approved": False})
        for synonym in synonyms:
            synonym_id = _node_id("GlossaryTerm", synonym)
            if synonym_id not in graph.nodes:
                graph.add_node(
                    synonym_id,
                    "GlossaryTerm",
                    {"name": synonym, "approved": False},
                )
            if synonym_id != canonical_id:
                graph.add_edge(synonym_id, "SYNONYM_OF", canonical_id)

    for metric_id, metric in metadata.metrics.items():
        domain_name = next(iter(domain_names))
        metric_node_id = _node_id("Metric", metric_id)
        source = metric["source"]
        graph.add_node(metric_node_id, "Metric", {"name": metric["name"]})
        _add_domain_edge(graph, _node_id("Domain", domain_name), metric_node_id)
        graph.add_edge(metric_node_id, "USES_DATASET", _node_id("Dataset", source["dataset"]))
        graph.add_edge(
            metric_node_id,
            "USES_COLUMN",
            _dataset_column_id(source["dataset"], source["column"]),
        )
    for dimension_id, dimension in metadata.dimensions.items():
        domain_name = next(iter(domain_names))
        dimension_node_id = _node_id("Dimension", dimension_id)
        source = dimension["source"]
        graph.add_node(dimension_node_id, "Dimension", {"name": dimension["name"]})
        _add_domain_edge(graph, _node_id("Domain", domain_name), dimension_node_id)
        graph.add_edge(dimension_node_id, "USES_DATASET", _node_id("Dataset", source["dataset"]))
        graph.add_edge(
            dimension_node_id,
            "USES_COLUMN",
            _dataset_column_id(source["dataset"], source["column"]),
        )

    for metric_id, metric in metadata.metrics.items():
        metric_node_id = _node_id("Metric", metric_id)
        for dimension_id in metric.get("allowed_dimensions", []):
            graph.add_edge(
                metric_node_id,
                "ALLOWED_DIMENSION",
                _node_id("Dimension", dimension_id),
            )

    for relationship_id, relationship in metadata.relationships.items():
        domain_name = next(iter(domain_names))
        relationship_node_id = _node_id("Relationship", relationship_id)
        graph.add_node(
            relationship_node_id,
            "Relationship",
            {"name": relationship["name"], "cardinality": relationship["cardinality"]},
        )
        _add_domain_edge(graph, _node_id("Domain", domain_name), relationship_node_id)
        graph.add_edge(
            relationship_node_id,
            "JOINS_TO",
            _node_id("Dataset", relationship["from"]["dataset"]),
            {"endpoint": "from"},
        )
        graph.add_edge(
            relationship_node_id,
            "JOINS_TO",
            _node_id("Dataset", relationship["to"]["dataset"]),
            {"endpoint": "to"},
        )

    for role_name, role in policies.roles.items():
        policy_id = _node_id("Policy", role_name)
        graph.add_node(policy_id, "Policy", {"role": role_name})
        for domain_name in role.get("domains", []):
            domain_id = _node_id("Domain", domain_name)
            if domain_id in graph.nodes:
                graph.add_edge(domain_id, "PROTECTED_BY", policy_id)
        for dataset_id in role.get("datasets", []):
            graph.add_edge(_node_id("Dataset", dataset_id), "PROTECTED_BY", policy_id)
        for metric_id in role.get("metrics", []):
            graph.add_edge(_node_id("Metric", metric_id), "PROTECTED_BY", policy_id)
        for column_id in role.get("columns", []) + role.get("denied_columns", []):
            graph.add_edge(_node_id("Column", column_id), "PROTECTED_BY", policy_id)

    return graph


if __name__ == "__main__":
    print(json.dumps(build_knowledge_graph().to_dict(), indent=2, sort_keys=True))
