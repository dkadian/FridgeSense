"""Request and response models.

Email is typed as a plain ``str`` with a local format check rather than
``pydantic.EmailStr``, which would pull in the ``email-validator`` package. For a
project that has to install cleanly from a short requirements file, one fewer
transitive dependency is worth more than RFC-complete address parsing.

Response bodies are mostly left as plain dicts. The service layer already
produces stable, documented shapes, and re-declaring twenty nested models here
would double the surface area to keep in sync without catching real bugs.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
STORAGES = ("pantry", "fridge", "freezer")
CONTAINERS = ("default", "airtight", "steel_dabba", "polythene", "paper_mesh", "open")


class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=200, description="Login address")
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field("", max_length=80)
    household_size: int = Field(3, ge=1, le=20,
                                description="People eating from this kitchen")

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class ProfileUpdate(BaseModel):
    name: str | None = Field(None, max_length=80)
    household_size: int | None = Field(None, ge=1, le=20)


class ItemCreate(BaseModel):
    food_id: str = Field(..., description="Catalog id, e.g. 'spinach'")
    grams: float | None = Field(None, gt=0, le=100000)
    count: float | None = Field(None, gt=0, le=500,
                                description="Number of catalog units instead of grams")
    storage: str | None = Field(None, description="pantry | fridge | freezer")
    container: str | None = Field("default", description="default | airtight | steel_dabba | polythene | paper_mesh | open")
    is_covered: bool | None = Field(True, description="Whether container is covered")
    purchase_date: str | None = Field(None, description="YYYY-MM-DD, defaults to today")
    expiry_date: str | None = Field(None, description="YYYY-MM-DD, defaults to shelf life")
    opened: bool = False
    notes: str = Field("", max_length=300)
    display_name: str | None = Field(None, max_length=80)

    @field_validator("storage")
    @classmethod
    def _storage(cls, v):
        if v is None:
            return v
        v = str(v).lower()
        if v not in STORAGES:
            raise ValueError("storage must be one of %s" % ", ".join(STORAGES))
        return v

    @field_validator("container")
    @classmethod
    def _container(cls, v):
        if v is None:
            return "default"
        v = str(v).lower()
        if v not in CONTAINERS:
            raise ValueError("container must be one of %s" % ", ".join(CONTAINERS))
        return v


class ItemBulkCreate(BaseModel):
    items: list[ItemCreate] = Field(..., min_length=1, max_length=200)


class ItemUpdate(BaseModel):
    display_name: str | None = Field(None, max_length=80)
    grams_remaining: float | None = Field(None, ge=0, le=100000)
    storage: str | None = None
    container: str | None = None
    is_covered: bool | None = None
    opened: bool | None = None
    purchase_date: str | None = None
    expiry_date: str | None = None
    notes: str | None = Field(None, max_length=300)

    @field_validator("storage")
    @classmethod
    def _storage(cls, v):
        if v is None:
            return v
        v = str(v).lower()
        if v not in STORAGES:
            raise ValueError("storage must be one of %s" % ", ".join(STORAGES))
        return v

    @field_validator("container")
    @classmethod
    def _container(cls, v):
        if v is None:
            return v
        v = str(v).lower()
        if v not in CONTAINERS:
            raise ValueError("container must be one of %s" % ", ".join(CONTAINERS))
        return v


class ResolveRequest(BaseModel):
    status: str = Field(..., description="consumed | wasted | donated")
    grams: float | None = Field(None, ge=0, le=100000,
                                description="Defaults to everything left")
    waste_reason: str = Field("", max_length=60)

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        v = str(v).lower()
        if v not in ("consumed", "wasted", "donated"):
            raise ValueError("status must be consumed, wasted or donated")
        return v


class CookRequest(BaseModel):
    servings: float | None = Field(None, gt=0, le=50)


class ReceiptParseRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    purchase_date: str | None = None


class ReceiptConfirmItem(BaseModel):
    food_id: str
    grams: float = Field(..., gt=0, le=100000)
    storage: str | None = None
    purchase_date: str | None = None
    expiry_date: str | None = None


class ReceiptConfirmRequest(BaseModel):
    items: list[ReceiptConfirmItem] = Field(..., min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class ImageParseRequest(BaseModel):
    image_base64: str = Field(..., description="Base64 encoded image string")
    mime_type: str = Field("image/jpeg", description="MIME type, e.g. image/jpeg, image/png")
    mode: str = Field("auto", description="auto | receipt | fridge")
    purchase_date: str | None = None


class AiRecipeGenerateRequest(BaseModel):
    meal: str = Field("any", description="any | breakfast | lunch | dinner | snack")
    diet: str = Field("any", description="any | vegetarian | vegan | nonveg")
    preferences: str = Field("", max_length=200, description="Optional taste or dietary preference")
    target_item_ids: list[int] | None = Field(None, description="Optional specific pantry item IDs to rescue")


class CustomRecipeCookItem(BaseModel):
    food_id: str
    grams: float = Field(..., gt=0, le=100000)


class CustomRecipeCookRequest(BaseModel):
    title: str = Field("Custom Recipe", max_length=120)
    ingredients: list[CustomRecipeCookItem] = Field(..., min_length=1, max_length=50)
    servings: float | None = Field(1.0, gt=0, le=50)


class AiCoachRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    history: list[dict] | None = None


class AiKeyRequest(BaseModel):
    api_key: str = Field(..., max_length=200)

