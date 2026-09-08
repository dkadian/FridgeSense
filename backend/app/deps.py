"""Shared FastAPI dependencies: a per-request database handle and the caller."""
from __future__ import annotations

import sqlite3

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db
from .knowledge import Knowledge, get_knowledge
from .repositories import users as users_repo
from .security import decode_token

bearer = HTTPBearer(auto_error=False, description="Paste the token from /api/auth/login")


def get_conn():
    """One connection per request, committed on success and always closed."""
    conn = db.connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_kn() -> Knowledge:
    return get_knowledge()


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing bearer token",
                            headers={"WWW-Authenticate": "Bearer"})
    payload = decode_token(credentials.credentials)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token is invalid or has expired",
                            headers={"WWW-Authenticate": "Bearer"})
    row = users_repo.by_id(conn, int(payload["sub"]))
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="This account no longer exists")
    return {"id": int(row["id"]), "email": row["email"], "name": row["name"],
            "household_size": int(row["household_size"]),
            "created_at": row["created_at"]}
