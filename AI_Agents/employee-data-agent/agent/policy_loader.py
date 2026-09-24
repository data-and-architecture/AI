"""
Loads the role -> permission mapping from config/security.yaml.

This is the prototype's source of truth for authorization. When the
platform moves beyond the prototype, this loader is the seam to swap
out for a client to a centralized policy engine (OPA/Rego and
friends) -- callers only ever deal with plain dicts keyed by role
name, never with YAML directly.
"""

from pathlib import Path
from typing import Any

import yaml


class PolicyLoader:

    def __init__(self, path: str = "config/security.yaml"):
        self.path = Path(path)
        self.roles: dict[str, Any] = {}

    def load(self) -> "PolicyLoader":
        if not self.path.exists():
            raise FileNotFoundError(f"Security policy file not found: {self.path}")

        with self.path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}

        self.roles = data.get("roles", {}) or {}
        return self

    def get_role(self, role_name: str) -> dict[str, Any] | None:
        return self.roles.get(role_name)
