"""User management and RBAC API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.deps import SessionDep, WorkspaceDep
from src.db.queries import (
    create_invitation,
    create_user,
    deactivate_user,
    get_user,
    list_invitations,
    list_users,
    update_user_role,
)
from src.logger import log

router = APIRouter(prefix="/api/v1/users", tags=["users"])

# Valid roles
VALID_ROLES = {"admin", "operator", "viewer"}


class CreateUserRequest(BaseModel):
    email: str = Field(..., min_length=3)
    name: str = Field(..., min_length=1, max_length=255)
    role: str = Field("viewer", pattern="^(admin|operator|viewer)$")


class UpdateRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(admin|operator|viewer)$")


class InviteUserRequest(BaseModel):
    email: str = Field(..., min_length=3)
    role: str = Field("viewer", pattern="^(admin|operator|viewer)$")


@router.get("")
async def list_users_route(
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """List all active users in the workspace."""
    users = await list_users(session=session, workspace_id=workspace_id)
    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "name": u.name,
                "role": u.role,
                "created_at": str(u.created_at) if u.created_at else None,
            }
            for u in users
        ],
        "total": len(users),
    }


@router.post("", status_code=201)
async def create_user_route(
    body: CreateUserRequest,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Add a user to the workspace."""
    log.info("api.create_user", workspace_id=workspace_id, email=body.email)
    user = await create_user(
        session=session,
        workspace_id=workspace_id,
        email=body.email,
        name=body.name,
        role=body.role,
    )
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
    }


@router.put("/{user_id}/role")
async def update_role_route(
    user_id: str,
    body: UpdateRoleRequest,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Update a user's role."""
    success = await update_user_role(
        session=session, user_id=user_id, workspace_id=workspace_id, role=body.role
    )
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "updated", "role": body.role}


@router.delete("/{user_id}")
async def remove_user_route(
    user_id: str,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Remove (deactivate) a user from the workspace."""
    success = await deactivate_user(
        session=session, user_id=user_id, workspace_id=workspace_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "deactivated"}


@router.post("/invite", status_code=201)
async def invite_user_route(
    body: InviteUserRequest,
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """Invite a user to the workspace."""
    invitation = await create_invitation(
        session=session,
        workspace_id=workspace_id,
        email=body.email,
        role=body.role,
        invited_by="system",  # TODO: get from auth context
    )
    return {
        "invitation_id": invitation.id,
        "email": invitation.email,
        "role": invitation.role,
        "status": "pending",
    }


@router.get("/invitations")
async def list_invitations_route(
    session: SessionDep,
    workspace_id: WorkspaceDep,
):
    """List pending invitations."""
    invitations = await list_invitations(session=session, workspace_id=workspace_id)
    return {
        "invitations": [
            {
                "id": i.id,
                "email": i.email,
                "role": i.role,
                "status": i.status,
                "created_at": str(i.created_at) if i.created_at else None,
            }
            for i in invitations
        ],
    }
