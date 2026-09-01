from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.constants import RoleCode


class HasRole(BasePermission):
    """Base for role gates. Subclasses set ``required_roles``; superusers always pass."""

    required_roles: frozenset[str] = frozenset()

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        roles = getattr(view, "required_roles", None) or self.required_roles
        return bool(roles & user.role_codes)


class OpsPermission(HasRole):
    """Everything under /ops/ inherits this, so a forgotten permission class fails closed."""

    required_roles = frozenset(
        {RoleCode.OPS_AGENT, RoleCode.TICKETING, RoleCode.FINANCE, RoleCode.SUPERADMIN}
    )


class OpsReadOnlyOrRole(OpsPermission):
    """See ``OpsPermission.has_permission``; safe methods need any ops role, writes need ``write_roles``."""

    write_roles: frozenset[str] = frozenset({RoleCode.OPS_AGENT, RoleCode.SUPERADMIN})

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        if request.method in SAFE_METHODS or request.user.is_superuser:
            return True
        return bool(
            (getattr(view, "write_roles", None) or self.write_roles) & request.user.role_codes
        )


class FinancePermission(HasRole):
    required_roles = frozenset({RoleCode.FINANCE, RoleCode.SUPERADMIN})


class TicketingPermission(HasRole):
    required_roles = frozenset({RoleCode.TICKETING, RoleCode.SUPERADMIN})
