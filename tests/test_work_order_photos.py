import pytest
from fastapi.testclient import TestClient

from field_photo_dispatch.work_order_photos import (
    PhotoUploadRequest,
    create_service,
    plan_photo_upload,
)


class RecordingStorage:
    def __init__(self) -> None:
        self.presign_calls: list[tuple[str, str]] = []

    def presign_photo(self, bucket: str, key: str, **_: object) -> dict[str, str]:
        self.presign_calls.append((bucket, key))
        return {"url": "https://uploads.example/photo"}


def test_startup_does_not_create_persistent_storage() -> None:
    storage = RecordingStorage()

    with TestClient(create_service(storage)):
        pass

    assert storage.presign_calls == []


def test_on_site_photo_moves_to_service_note_follow_up() -> None:
    request = PhotoUploadRequest(
        work_order_id="WO-1842",
        technician_id="tech-27",
        dispatch_status="on_site",
        filename="compressor panel.jpg",
        content_type="image/jpeg",
        size_bytes=2_400_000,
    )

    key, follow_up = plan_photo_upload(request)

    assert key == "work-orders/WO-1842/tech-27/compressor-panel.jpg"
    assert follow_up == "Add the service note after the photo finishes uploading"


def test_completed_order_does_not_mint_an_upload() -> None:
    request = PhotoUploadRequest(
        work_order_id="WO-1842",
        technician_id="tech-27",
        dispatch_status="completed",
        filename="late.jpg",
        content_type="image/jpeg",
        size_bytes=120_000,
    )

    with pytest.raises(ValueError, match="en route or on site"):
        plan_photo_upload(request)
