from agent.security_context import (
    SecurityContext,
    UserIdentity,
)


class AuthenticationService:

    def authenticate(
        self,
        token: str
    ) -> SecurityContext:

        # Prototype only.
        # Replace with Okta / Entra ID / Keycloak later.

        if not token:
            return SecurityContext(
                authenticated=False
            )

        roles = ["DATA_ANALYST"]
        if token == "technical-token":
            roles.append("DATA_ENGINEER")
        if token == "admin-token":
            roles.extend(["DATA_ENGINEER", "DATA_ADMIN"])

        return SecurityContext(
            authenticated=True,

            user=UserIdentity(
                user_id="user-001",
                username="ravi",
                roles=roles,
                groups=[
                    "HR_ANALYTICS"
                ]
            )
        )