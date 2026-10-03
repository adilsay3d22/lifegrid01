"""Role and site-scope checks shared by every router (SEC-05, FR-AUTH-04). Deny by default."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.enums import Role
from app.core.errors import Problem
from app.core.security import read_jwt


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    role: Role
    email: str | None
    site_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)

    @property
    def region_wide(self) -> bool:
        # v1 has one region, so region-scoped roles see every site (spec section 3).
        return self.role in (Role.bank_manager, Role.admin, Role.auditor, Role.donor_coordinator)

    def can_see_site(self, site_id: uuid.UUID) -> bool:
        return self.region_wide or site_id in self.site_ids

    def require_site(self, site_id: uuid.UUID) -> None:
        if not self.can_see_site(site_id):
            raise Problem(403, "out_of_scope", "You do not have access to this site.")


def get_principal(request: Request, db: Session = Depends(get_db)) -> Principal:  # noqa: B008
    from app.modules.auth.models import AppUser  # local import keeps core free of module imports at load

    header = request.headers.get("authorization", "")
    claims = read_jwt(header[7:], "access") if header.lower().startswith("bearer ") else None
    if not claims:
        raise Problem(401, "unauthenticated", "Sign in to continue.")
    user = db.get(AppUser, uuid.UUID(claims["sub"]))
    # Checked on every request, so disabling a user ends their sessions immediately (FR-ADM-01).
    if not user or not user.active:
        raise Problem(401, "unauthenticated", "Your session has ended.")
    return Principal(user.id, user.role, user.email, frozenset(user.site_ids))


def require(*roles: Role) -> Callable[..., Principal]:
    allowed = set(roles)

    def dep(p: Principal = Depends(get_principal)) -> Principal:
        if p.role not in allowed:
            raise Problem(403, "forbidden_role", "Your role cannot do this.")
        return p

    dep.__lifegrid_auth__ = True  # type: ignore[attr-defined]  # marker for the deny-by-default test
    return dep


STAFF = (Role.bank_manager, Role.hospital_lead, Role.donor_coordinator, Role.admin, Role.auditor)


get_principal.__lifegrid_auth__ = True  # type: ignore[attr-defined]
