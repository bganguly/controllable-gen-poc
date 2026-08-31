from __future__ import annotations

import hashlib
import logging
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import APIKey, get_db
from app.models.schemas import CreateKeyRequest, CreateKeyResponse, KeyInfo
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _require_master(authorization: str = Header(...)) -> None:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header must be: Bearer <key>")
    key = authorization[7:]
    if key != get_settings().gateway_master_key:
        raise HTTPException(status_code=403, detail="Invalid master key")


@router.post("/keys", status_code=201, response_model=CreateKeyResponse)
async def create_key(
    body: CreateKeyRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_master),
) -> CreateKeyResponse:
    raw_key = f"gw_{secrets.token_hex(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    api_key = APIKey(
        key_hash=key_hash,
        owner=body.owner,
        allowed_models=body.allowed_models,
        rate_limit_tier=body.rate_limit_tier,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    logger.info("api_key_created", extra={"owner": body.owner, "id": str(api_key.id)})
    return CreateKeyResponse(
        key=raw_key,
        id=str(api_key.id),
        owner=api_key.owner,
        rate_limit_tier=api_key.rate_limit_tier,
    )


@router.get("/keys", response_model=list[KeyInfo])
async def list_keys(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_master),
) -> list[KeyInfo]:
    result = await db.execute(select(APIKey).order_by(APIKey.created_at.desc()))
    rows = result.scalars().all()
    return [
        KeyInfo(
            id=str(r.id),
            owner=r.owner,
            allowed_models=r.allowed_models,
            rate_limit_tier=r.rate_limit_tier,
            created_at=r.created_at.isoformat(),
            is_active=r.is_active,
        )
        for r in rows
    ]


@router.get("/keys/{key_id}", response_model=KeyInfo)
async def get_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_master),
) -> KeyInfo:
    result = await db.execute(select(APIKey).where(APIKey.id == UUID(key_id)))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return KeyInfo(
        id=str(row.id),
        owner=row.owner,
        allowed_models=row.allowed_models,
        rate_limit_tier=row.rate_limit_tier,
        created_at=row.created_at.isoformat(),
        is_active=row.is_active,
    )


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_master),
) -> None:
    result = await db.execute(select(APIKey).where(APIKey.id == UUID(key_id)))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Key not found")
    row.is_active = False
    await db.commit()
    logger.info("api_key_revoked", extra={"id": key_id})
