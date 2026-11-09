from dataclasses import dataclass

from app.application.errors import forbidden

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "applicant": frozenset({"application:create", "application:read_own", "vehicle:read", "policy:read"}),
    "loan_officer": frozenset({
        "application:create", "application:read_all", "vehicle:read", "policy:read", "audit:read",
    }),
    "policy_admin": frozenset({
        "policy:read", "policy:write", "policy:publish", "policy_document:read", "vehicle:read", "audit:read",
    }),
    "tenant_admin": frozenset({"application:read_all", "policy:read", "policy_document:read", "vehicle:read",
                               "audit:read"}),
}


@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str
    display_name: str
    tenant_id: str  # derived from verified membership, never trusted from the client alone
    roles: frozenset[str]
    available_tenants: tuple[str, ...]

    @property
    def permissions(self) -> frozenset[str]:
        perms: set[str] = set()
        for role in self.roles:
            perms |= ROLE_PERMISSIONS.get(role, frozenset())
        return frozenset(perms)

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def require(self, permission: str) -> None:
        if not self.has(permission):
            raise forbidden(f"Missing permission '{permission}'")

    def can_read_application(self, applicant_user_id: str) -> bool:
        return self.has("application:read_all") or (
            self.has("application:read_own") and applicant_user_id == self.user_id
        )
