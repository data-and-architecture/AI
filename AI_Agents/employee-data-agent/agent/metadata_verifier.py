from agent.metadata_loader import MetadataLoader
from agent.metadata_context import MetadataContext

class MetadataVerifier:

    def __init__(self, metadata: MetadataLoader):
        self.metadata = metadata

    def verify(self, context: MetadataContext) -> MetadataContext:

        verified = MetadataContext()

        for metric in context.metrics:

            metric_id = metric.get("id")

            if metric_id in self.metadata.metrics:
                verified.metrics.append(
                    self.metadata.get_metric(metric_id)
                )

        for dimension in context.dimensions:

            dimension_id = dimension.get("id")

            if dimension_id in self.metadata.dimensions:
                verified.dimensions.append(
                    self.metadata.get_dimension(dimension_id)
                )

        for dataset in context.datasets:

            dataset_id = dataset.get("id")

            if dataset_id in self.metadata.datasets:
                verified.datasets.append(
                    self.metadata.get_dataset(dataset_id)
                )

        for relationship in context.relationships:

            relationship_id = relationship.get("id")

            if relationship_id in self.metadata.relationships:
                verified.relationships.append(
                    self.metadata.get_relationship(
                        relationship_id
                    )
                )

        for column in context.columns:

            column_id = column.get("id")

            if column_id in self.metadata.columns:
                verified.columns.append(
                    self.metadata.get_column(column_id)
                )

        for term in context.glossary_terms:

            term_id = term.get("id")

            if term_id in self.metadata.terms:
                verified.glossary_terms.append(
                    self.metadata.get_term(term_id)
                )

        return verified