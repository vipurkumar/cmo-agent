"""Email/password authentication for dashboard login.

Endpoints:
- POST /auth/register — create account (first user becomes admin)
- POST /auth/login — email/password login, returns session token
- POST /auth/logout — invalidate session
- GET /auth/me — get current user info
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, String, select, text, update
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.api.deps import SessionDep
from src.db.queries import Base, Workspace, async_session_factory, create_workspace
from src.logger import log

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------

class UserCredential(Base):
    __tablename__ = "user_credentials"
    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    workspace_id = Column(PG_UUID(as_uuid=False), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    user_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    role: Mapped[str] = mapped_column(String, nullable=False, default="viewer")
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))
    last_login_at = Column(DateTime(timezone=True), nullable=True)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("gen_random_uuid()"))
    workspace_id = Column(PG_UUID(as_uuid=False), nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    token: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)
    name: str = Field(..., min_length=1)
    company: str = Field("", description="Company name for workspace")


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return f"{salt}:{hashed}"


def _verify_password(password: str, stored: str) -> bool:
    salt, hashed = stored.split(":")
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return check == hashed


def _generate_session_token() -> str:
    return f"sess_{secrets.token_urlsafe(48)}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", status_code=201)
async def register(body: RegisterRequest, session: SessionDep):
    """Register a new account. Creates a workspace and user."""
    log.info("auth.register", email=body.email)

    # Check if email already exists
    existing = await session.execute(
        select(UserCredential).where(UserCredential.email == body.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    # Create workspace
    workspace = await create_workspace(
        session=session,
        name=body.company or f"{body.name}'s Workspace",
        plan="free",
    )

    # Create user credential
    cred = UserCredential(
        workspace_id=workspace.id,
        email=body.email,
        password_hash=_hash_password(body.password),
        user_name=body.name,
        role="admin",  # First user is admin
    )
    session.add(cred)
    await session.flush()

    # Create session token
    token = _generate_session_token()
    login_session = LoginSession(
        workspace_id=workspace.id,
        email=body.email,
        token=token,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    session.add(login_session)
    await session.flush()

    log.info("auth.registered", email=body.email, workspace_id=str(workspace.id))

    return {
        "token": token,
        "user": {
            "email": body.email,
            "name": body.name,
            "role": "admin",
            "workspace_id": str(workspace.id),
            "workspace_name": workspace.name,
        },
    }


@router.post("/login")
async def login(body: LoginRequest, session: SessionDep):
    """Login with email and password. Returns a session token."""
    log.info("auth.login_attempt", email=body.email)

    result = await session.execute(
        select(UserCredential).where(UserCredential.email == body.email)
    )
    cred = result.scalar_one_or_none()

    if not cred or not _verify_password(body.password, cred.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Get workspace name
    ws_result = await session.execute(
        select(Workspace).where(Workspace.id == cred.workspace_id)
    )
    workspace = ws_result.scalar_one_or_none()

    # Create session token
    token = _generate_session_token()
    login_session = LoginSession(
        workspace_id=cred.workspace_id,
        email=cred.email,
        token=token,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    session.add(login_session)

    # Update last login
    await session.execute(
        update(UserCredential)
        .where(UserCredential.id == cred.id)
        .values(last_login_at=datetime.now(UTC))
    )
    await session.flush()

    log.info("auth.login_success", email=body.email)

    return {
        "token": token,
        "user": {
            "email": cred.email,
            "name": cred.user_name,
            "role": cred.role,
            "workspace_id": str(cred.workspace_id),
            "workspace_name": workspace.name if workspace else "",
        },
    }


@router.post("/logout")
async def logout(session: SessionDep):
    """Logout — placeholder, client should discard token."""
    return {"status": "logged_out"}


@router.get("/me")
async def get_me(session: SessionDep):
    """Get current user info from session token. Placeholder — returns 401 if no valid session."""
    raise HTTPException(status_code=401, detail="No session — use token from login response")
