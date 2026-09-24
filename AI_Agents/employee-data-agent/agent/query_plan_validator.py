class QueryPlanValidationError(Exception):
    pass


class QueryPlanValidator:

    def __init__(self, metadata):

        self.metadata = metadata

    def validate(  self,        plan,        metadata_context    ):

        self.validate_metric(    plan,            metadata_context        )

        self.validate_dimensions(            plan,            metadata_context        )

        self.validate_datasets(            plan,            metadata_context        )

        self.validate_relationships(            plan,            metadata_context        )

        self.validate_filters(            plan,            metadata_context        )

        self.validate_metric_dimensions(            plan,            metadata_context        )

        return plan


    def validate_metric(    self,    plan,    context):
        metric_ids = {
            metric["id"]
            for metric in context.metrics
        }

        if plan.metric_id not in metric_ids:
            raise QueryPlanValidationError(
                f"Metric not found in verified metadata: "
                f"{plan.metric_id}"
            )   

    def validate_dimensions(    self,    plan,    context):

        valid_dimensions = {
            dimension["id"]
            for dimension in context.dimensions
        }

        for dimension_id in plan.dimension_ids:

            if dimension_id not in valid_dimensions:

                raise QueryPlanValidationError(
                    f"Dimension not found: "
                    f"{dimension_id}"
                )

    def validate_datasets(    self,    plan,    context ):

        valid_datasets = {
            dataset["id"]
            for dataset in context.datasets
        }

        for dataset_id in plan.dataset_ids:

            if dataset_id not in valid_datasets:

                raise QueryPlanValidationError(
                    f"Dataset not approved: "
                    f"{dataset_id}"


                )    


    def validate_relationships(
        self,
        plan,
        context
    ):

        valid_relationships = {
            relationship["id"]
            for relationship
            in context.relationships
        }

        for relationship_id in plan.relationship_ids:

            if relationship_id not in valid_relationships:

                raise QueryPlanValidationError(
                    f"Relationship not approved: "
                    f"{relationship_id}"
                )

    def validate_metric_dimensions(
    self,
    plan,
    context
    ):

        metric = next(
            metric
            for metric in context.metrics
            if metric["id"] == plan.metric_id
        )

        allowed_dimensions = set(
            metric.get(
                "allowed_dimensions",
                []
            )
        )

        for dimension_id in plan.dimension_ids:

            if dimension_id not in allowed_dimensions:

                raise QueryPlanValidationError(
                    f"Dimension '{dimension_id}' "
                    f"is not allowed for metric "
                    f"'{plan.metric_id}'"
                )

    def validate_filters(
    self,
    plan,
    context
    ):

        valid_columns = {
            column["id"]
            for column in context.columns
        }

        allowed_operators = {
            "=",
            "!=",
            ">",
            ">=",
            "<",
            "<=",
            "IN",
            "LIKE"
        }

        for filter_item in plan.filters:

            if filter_item.column_id not in valid_columns:

                raise QueryPlanValidationError(
                    f"Filter column not approved: "
                    f"{filter_item.column_id}"
                )

            if filter_item.operator not in allowed_operators:

                raise QueryPlanValidationError(
                    f"Operator not allowed: "
                    f"{filter_item.operator}"
                )
        

    def check_datasets(    plan,    security_context    ):

        allowed = set(        security_context.allowed_datasets    )

        for dataset_id in plan.dataset_ids:

            if dataset_id not in allowed:

                return False, (
                    f"Dataset access denied: "
                    f"{dataset_id}"
                )

        return True, None                     


    def check_metric(
    plan,
    security_context
    ):

        if (
            plan.metric_id
            not in security_context.allowed_metrics
        ):

            return False, (
                f"Metric access denied: "
                f"{plan.metric_id}"
            )

        return True, None

    