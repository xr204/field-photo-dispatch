from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .infrai_storage import InfraiError, InfraiStorage

BUCKET = os.environ.get("INFRAI_PHOTO_BUCKET", "field-work-order-photos")
SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


class PhotoUploadRequest(BaseModel):
    work_order_id: str = Field(min_length=1, max_length=80)
    technician_id: str = Field(min_length=1, max_length=80)
    dispatch_status: Literal["assigned", "en_route", "on_site", "completed"]
    filename: str = Field(min_length=1, max_length=160)
    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    size_bytes: int = Field(gt=0, le=10_000_000)


class PhotoUploadResponse(BaseModel):
    upload_url: str
    method: Literal["PUT"] = "PUT"
    object_key: str
    next_dispatch_status: Literal["photo_upload_pending"] = "photo_upload_pending"
    technician_follow_up: str


def plan_photo_upload(request: PhotoUploadRequest) -> tuple[str, str]:
    if request.dispatch_status not in {"en_route", "on_site"}:
        raise ValueError("Photo evidence is accepted while the technician is en route or on site")
    filename = SAFE_NAME.sub("-", request.filename).strip(".-") or "photo"
    key = f"work-orders/{request.work_order_id}/{request.technician_id}/{filename}"
    follow_up = (
        "Confirm arrival after the photo finishes uploading"
        if request.dispatch_status == "en_route"
        else "Add the service note after the photo finishes uploading"
    )
    return key, follow_up


def create_service(storage: InfraiStorage | None = None) -> FastAPI:
    storage_client = storage

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        nonlocal storage_client
        storage_client = storage_client or InfraiStorage()
        yield

    app = FastAPI(title="Field photo dispatch", lifespan=lifespan)

    @app.post("/work-orders/photo-upload", response_model=PhotoUploadResponse)
    def request_photo_upload(request: PhotoUploadRequest) -> PhotoUploadResponse:
        if storage_client is None:
            raise HTTPException(status_code=503, detail="Storage setup is still starting")
        try:
            key, follow_up = plan_photo_upload(request)
            signed = storage_client.presign_photo(
                BUCKET,
                key,
                content_type=request.content_type,
                max_bytes=request.size_bytes,
                idempotency_key=f"{request.work_order_id}:{request.technician_id}:{key}",
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InfraiError as exc:
            client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
            raise HTTPException(status_code=client_status, detail=exc.details) from exc
        return PhotoUploadResponse(
            upload_url=str(signed["url"]),
            object_key=key,
            technician_follow_up=follow_up,
        )

    return app


service = create_service()
