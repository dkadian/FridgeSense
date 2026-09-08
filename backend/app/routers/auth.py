from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import current_user, get_conn
from ..repositories import users as users_repo
from ..schemas import LoginRequest, ProfileUpdate, RegisterRequest, TokenResponse
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _public(row) -> dict:
    return {"id": int(row["id"]), "email": row["email"], "name": row["name"],
            "household_size": int(row["household_size"]), "created_at": row["created_at"]}


@router.post("/register", response_model=TokenResponse,
             status_code=status.HTTP_201_CREATED, summary="Create an account")
def register(payload: RegisterRequest, conn: sqlite3.Connection = Depends(get_conn)):
    if users_repo.by_email(conn, payload.email) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="That email is already registered")
    user_id = users_repo.create(conn, payload.email, payload.name,
                                hash_password(payload.password), payload.household_size)
    row = users_repo.by_id(conn, user_id)
    return {"access_token": create_token(user_id, payload.email),
            "token_type": "bearer", "user": _public(row)}


@router.post("/login", response_model=TokenResponse, summary="Exchange credentials for a token")
def login(payload: LoginRequest, conn: sqlite3.Connection = Depends(get_conn)):
    row = users_repo.by_email(conn, payload.email)
    # Same message either way: revealing which half was wrong helps an attacker
    # enumerate valid addresses.
    if row is None or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Incorrect email or password")
    return {"access_token": create_token(int(row["id"]), row["email"]),
            "token_type": "bearer", "user": _public(row)}


@router.get("/me", summary="The signed-in user")
def me(user: dict = Depends(current_user)):
    return user


@router.patch("/me", summary="Update name or household size")
def update_me(payload: ProfileUpdate, user: dict = Depends(current_user),
              conn: sqlite3.Connection = Depends(get_conn)):
    users_repo.update_profile(conn, user["id"], payload.name, payload.household_size)
    return _public(users_repo.by_id(conn, user["id"]))
