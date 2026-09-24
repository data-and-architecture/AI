import unittest

from agent.knowledge_graph import EDGE_TYPES, NODE_TYPES, KnowledgeGraph, build_knowledge_graph


class KnowledgeGraphTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.graph = build_knowledge_graph()

    def _has_edge(self, source, edge_type, target, **properties):
        return any(
            edge.source_id == source
            and edge.edge_type == edge_type
            and edge.target_id == target
            and all(edge.properties.get(key) == value for key, value in properties.items())
            for edge in self.graph.edges
        )

    def test_contains_every_requested_node_and_edge_type(self):
        node_types = {node.node_type for node in self.graph.nodes.values()}
        edge_types = {edge.edge_type for edge in self.graph.edges}

        self.assertEqual(node_types, NODE_TYPES)
        self.assertEqual(edge_types, EDGE_TYPES)

    def test_semantic_and_catalog_links_are_projected_from_metadata(self):
        self.assertTrue(
            self._has_edge("metric:employee_count", "USES_DATASET", "dataset:employees")
        )
        self.assertTrue(
            self._has_edge(
                "metric:employee_count", "USES_COLUMN", "column:employees.employee_id"
            )
        )
        self.assertTrue(
            self._has_edge(
                "metric:employee_count", "ALLOWED_DIMENSION", "dimension:department"
            )
        )
        self.assertTrue(
            self._has_edge("dimension:department", "USES_DATASET", "dataset:departments")
        )
        self.assertTrue(
            self._has_edge("dataset:employees", "DEFINES", "column:employees.email")
        )

    def test_relationship_glossary_owner_and_policy_links_are_projected(self):
        self.assertTrue(
            self._has_edge(
                "relationship:employee_department",
                "JOINS_TO",
                "dataset:employees",
                endpoint="from",
            )
        )
        self.assertTrue(
            self._has_edge(
                "relationship:employee_department",
                "JOINS_TO",
                "dataset:departments",
                endpoint="to",
            )
        )
        self.assertTrue(
            self._has_edge("glossaryterm:staff", "SYNONYM_OF", "glossaryterm:employee")
        )
        self.assertTrue(
            self._has_edge("dataset:employees", "OWNED_BY", "owner:HR Analytics")
        )
        self.assertTrue(
            self._has_edge(
                "column:employees.salary", "PROTECTED_BY", "policy:DATA_ANALYST"
            )
        )

    def test_export_has_only_existing_edge_endpoints(self):
        exported = self.graph.to_dict()
        exported_node_ids = {node["id"] for node in exported["nodes"]}

        self.assertEqual(len(exported["nodes"]), len(self.graph.nodes))
        self.assertEqual(len(exported["edges"]), len(self.graph.edges))
        for edge in exported["edges"]:
            self.assertIn(edge["source"], exported_node_ids)
            self.assertIn(edge["target"], exported_node_ids)

    def test_rejects_invalid_graph_vocabulary_and_missing_endpoints(self):
        graph = KnowledgeGraph()
        with self.assertRaises(ValueError):
            graph.add_node("invalid", "Unknown")

        graph.add_node("domain:HR", "Domain")
        with self.assertRaises(ValueError):
            graph.add_edge("domain:HR", "DEFINES", "missing")
        with self.assertRaises(ValueError):
            graph.add_edge("domain:HR", "UNKNOWN", "domain:HR")


if __name__ == "__main__":
    unittest.main()
