"""Pydantic contracts for user accounts and authentication (IRA-33)."""

from __future__ import annotations

import time
import uuid

from pydantic import BaseModel, Field


class User(BaseModel):
    """A local account. Every project, uploaded document and share is owned by one."""

    id: str = Field(default_factory=lambda: f"usr_{uuid.uuid4().hex[:16]}")
    email: str
    display_name: str = ""
    is_admin: bool = False
    created_at: float = Field(default_factory=time.time)


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)
    display_name: str = Field(default="", max_length=80)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class MeResponse(BaseModel):
    user: User


class OwnedDocument(BaseModel):
    """One user's ownership of a content-addressed document (the same doc_id may have several owners
    when different users upload identical files)."""

    user_id: str
    doc_id: str
    filename: str
    path: str
    created_at: float = Field(default_factory=time.time)
