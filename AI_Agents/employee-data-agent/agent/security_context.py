from pydantic import BaseModel, Field


class UserIdentity(BaseModel):

    user_id: str

    username: str

    roles: list[str] = Field(
        default_factory=list
    )

    groups: list[str] = Field(
        default_factory=list
    )


class SecurityContext(BaseModel):

    authenticated: bool = False

    user: UserIdentity | None = None

    domains: list[str] = Field(
        default_factory=list
    )

    allowed_datasets: list[str] = Field(
        default_factory=list
    )

    allowed_columns: list[str] = Field(
        default_factory=list
    )

    denied_columns: list[str] = Field(
        default_factory=list
    )

    allowed_metrics: list[str] = Field(
        default_factory=list
    )

    denied_metrics: list[str] = Field(
        default_factory=list
    )

    can_view_sql: bool = False

    can_view_admin: bool = False