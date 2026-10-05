import uuid
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.rbac import has_permission
from app.models import Tenant, User
from app.models.enums import Role

bearer = HTTPBearer(auto_error=False)


@dataclass
class Actor:
    """The authenticated caller plus request metadata used for audit."""

    user: User
    ip: str | None
    user_agent: str | None

    @property
    def id(self) -> uuid.UUID:
        return self.user.id

    @property
    def tenant_id(self) -> uuid.UUID:
        if self.user.tenant_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This action requires a tenant user")
        return self.user.tenant_id

    @property
    def role(self) -> str:
        return self.user.role

    def can(self, permission: str) -> bool:
        return has_permission(self.user.role, permission)

    def is_manager(self) -> bool:
        return self.user.role in (Role.LAYOUT_ADMIN, Role.SUPERVISOR)


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def get_actor(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> Actor:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    if creds is None:
        raise unauthorized
    try:
        from app.core.security import decode_access_token

        payload = decode_access_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized
    user = db.get(User, user_id)
    if user is None or not user.is_active or payload.get("ver") != user.token_version:
        raise unauthorized
    if user.tenant_id is not None:
        tenant = db.get(Tenant, user.tenant_id)
        if tenant is None or tenant.status != "active":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant is not active")
    return Actor(user=user, ip=client_ip(request), user_agent=request.headers.get("user-agent"))


CurrentActor = Annotated[Actor, Depends(get_actor)]
DB = Annotated[Session, Depends(get_db)]


def require(permission: str):
    def checker(actor: CurrentActor) -> Actor:
        if not actor.can(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission}")
        return actor

    return checker


def Perm(permission: str):  # noqa: N802 - reads like a type in signatures
    return Annotated[Actor, Depends(require(permission))]
