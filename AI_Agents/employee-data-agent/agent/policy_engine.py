"""
Centralized Policy and Security Gate (Phase 6).

Every governed decision -- dataset access, column access, row-level
restriction, column masking, metric authorization, and resource
limits -- is made here, in one place, from data (security.yaml +
the catalog/semantic metadata), and NEVER inside an LLM prompt.

This module is an in-process prototype rule evaluator. When the
platform moves beyond the prototype, replace the body of
`PolicyEngine.evaluate()` with a call to a centralized policy
engine such as OPA/Rego. The `SecurityContext` / `PolicyDecision`
contracts are the seam: nothing else in the graph needs to change
when that swap happens.

Fail-closed: any error while resolving permissions or evaluating a
plan results in `PolicyDecision(allowed=False, ...)`, never an
implicit allow.
"""

from agent.metadata_loader import MetadataLoader
from agent.policy_decision import MaskingRule, PolicyDecision, ResourceLimits, RowFilter
from agent.policy_loader import PolicyLoader
from agent.security_context import SecurityContext, UserIdentity

metadata = MetadataLoader("metadata").load()


class PolicyEngine:

    def __init__(self, policy_path: str = "config/security.yaml"):
        self._policy_path = policy_path
        self._loader: PolicyLoader | None = None

    def _policies(self) -> PolicyLoader:
        if self._loader is None:
            self._loader = PolicyLoader(self._policy_path).load()
        return self._loader

    # ------------------------------------------------------------------
    # Resolve roles/groups -> domain permissions.
    # ------------------------------------------------------------------
    def build_security_context(self, user: UserIdentity | None) -> SecurityContext:
        if user is None:
            return SecurityContext(authenticated=False)

        try:
            policies = self._policies()
        except Exception:
            # Fail closed: no policy file, no access.
            return SecurityContext(authenticated=True, user=user)

        domains: set[str] = set()
        allowed_datasets: set[str] = set()
        allowed_columns: set[str] = set()
        denied_columns: set[str] = set()
        allowed_metrics: set[str] = set()
        denied_metrics: set[str] = set()
        can_view_sql = False
        can_view_admin = False

        for role_name in user.roles:
            role = policies.get_role(role_name)
            if not role:
                continue
            domains.update(role.get("domains", []))
            allowed_datasets.update(role.get("datasets", []))
            allowed_columns.update(role.get("columns", []))
            denied_columns.update(role.get("denied_columns", []))
            allowed_metrics.update(role.get("metrics", []))
            denied_metrics.update(role.get("denied_metrics", []))
            can_view_sql = can_view_sql or role.get("can_view_sql", False)
            can_view_admin = can_view_admin or role.get("can_view_admin", False)

        return SecurityContext(
            authenticated=True,
            user=user,
            domains=sorted(domains),
            allowed_datasets=sorted(allowed_datasets),
            allowed_columns=sorted(allowed_columns),
            denied_columns=sorted(denied_columns),
            allowed_metrics=sorted(allowed_metrics),
            denied_metrics=sorted(denied_metrics),
            can_view_sql=can_view_sql,
            can_view_admin=can_view_admin,
        )

    # ------------------------------------------------------------------
    # Evaluate a query plan against a security context.
    # ------------------------------------------------------------------
    def evaluate(self, plan: dict, security_context: SecurityContext) -> PolicyDecision:
        try:
            return self._evaluate(plan, security_context)
        except Exception as exc:
            # Fail closed: policy evaluation being unavailable/broken
            # is a denial, never a pass-through.
            return PolicyDecision(
                allowed=False,
                reason=f"Policy evaluation unavailable: {exc}",
            )

    def _evaluate(self, plan: dict, security_context: SecurityContext) -> PolicyDecision:
        if not security_context.authenticated or security_context.user is None:
            return PolicyDecision(allowed=False, reason="User is not authenticated")

        if not security_context.user.roles:
            return PolicyDecision(allowed=False, reason="User has no assigned roles")

        dataset_ids = plan.get("datasets", [])
        metric_id = plan.get("metric")

        # ---- dataset access -------------------------------------------------
        allowed_datasets = set(security_context.allowed_datasets)
        for dataset_id in dataset_ids:
            if dataset_id not in allowed_datasets:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Dataset access denied: {dataset_id}",
                )

        # ---- metric authorization --------------------------------------------
        if metric_id:
            if metric_id in security_context.denied_metrics:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Metric access explicitly denied: {metric_id}",
                )
            if metric_id not in security_context.allowed_metrics:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Metric access denied: {metric_id}",
                )

        # ---- column access ------------------------------------------------------
        allowed_columns = set(security_context.allowed_columns)
        denied_columns = set(security_context.denied_columns)

        for column_id in self._referenced_columns(plan):
            if column_id in denied_columns:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Column access denied: {column_id}",
                )
            if allowed_columns and column_id not in allowed_columns:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Column not authorized: {column_id}",
                )

        # ---- row-level restrictions + masking + limits --------------------------
        row_filters = self._row_filters(security_context, dataset_ids)
        masking_rules = self._masking_rules(security_context)
        limits = self._resource_limits(security_context)

        return PolicyDecision(
            allowed=True,
            reason=None,
            row_filters=row_filters,
            masking_rules=masking_rules,
            limits=limits,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _referenced_columns(self, plan: dict) -> set[str]:
        """Every catalog column ("dataset.column") the plan touches."""

        columns: set[str] = set()

        metric = metadata.get_metric(plan.get("metric")) if plan.get("metric") else None
        if metric:
            source = metric.get("source", {})
            if source.get("dataset") and source.get("column"):
                columns.add(f"{source['dataset']}.{source['column']}")
            for metric_filter in metric.get("filters", []):
                field = metric_filter.get("field")
                if field:
                    columns.add(field)

        for dimension_id in plan.get("dimensions", []):
            dimension = metadata.get_dimension(dimension_id)
            if not dimension:
                continue
            source = dimension.get("source", {})
            if source.get("dataset") and source.get("column"):
                columns.add(f"{source['dataset']}.{source['column']}")

        for plan_filter in plan.get("filters", []):
            column_ref = plan_filter.get("column")
            if column_ref and "." in column_ref:
                columns.add(column_ref)

        return columns

    def _role_configs(self, security_context: SecurityContext) -> list[dict]:
        policies = self._policies()
        configs = []
        for role_name in security_context.user.roles:
            role = policies.get_role(role_name)
            if role:
                configs.append(role)
        return configs

    def _row_filters(
    self,
    security_context: SecurityContext,
    dataset_ids: list[str],
    ) -> list[RowFilter]:
        filters: list[RowFilter] = []

        for role in self._role_configs(security_context):
            for row_filter in role.get("row_filters", []):
                dataset = row_filter["dataset"]

                if dataset not in dataset_ids:
                    continue

                filters.append(
                    RowFilter(
                        dataset_id=dataset,
                        column_id=row_filter["column"],
                        operator=row_filter["operator"],
                        value=row_filter["value"],
                    )
                )

        return filters

    def _masking_rules(self, security_context: SecurityContext) -> list[MaskingRule]:
        rules: dict[str, MaskingRule] = {}
        for role in self._role_configs(security_context):
            for masking in role.get("masking", []):
                rules[masking["column"]] = MaskingRule(
                    column_id=masking["column"],
                    strategy=masking["strategy"],
                )
        return list(rules.values())

    def _resource_limits(self, security_context: SecurityContext) -> ResourceLimits:
        # Most restrictive limit across all of the user's roles wins.
        limits = ResourceLimits()
        for role in self._role_configs(security_context):
            role_limits = role.get("limits", {})
            if "max_rows" in role_limits:
                limits.max_rows = min(limits.max_rows, role_limits["max_rows"])
            if "max_scan_mb" in role_limits:
                limits.max_scan_mb = min(limits.max_scan_mb, role_limits["max_scan_mb"])
            if "max_execution_seconds" in role_limits:
                limits.max_execution_seconds = min(
                    limits.max_execution_seconds, role_limits["max_execution_seconds"]
                )
        return limits
