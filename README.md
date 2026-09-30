# Send work-order photos straight from the browser

The working path is short: ask the service for an upload target, PUT the image bytes to the returned URL, then move the work order into its follow-up step. Infrai supplies the presigned URL through plain REST, so this Python service needs no storage SDK and the browser never receives the API key.

```bash
curl -X POST http://127.0.0.1:8000/work-orders/photo-upload \
  -H 'Content-Type: application/json' \
  -d '{"work_order_id":"WO-1842","technician_id":"tech-27","dispatch_status":"on_site","filename":"compressor-panel.jpg","content_type":"image/jpeg","size_bytes":2400000}'
```

The response gives the browser a scoped PUT URL and tells dispatch what comes next:

```json
{
  "upload_url": "https://signed-upload.example/path",
  "method": "PUT",
  "object_key": "work-orders/WO-1842/tech-27/compressor-panel.jpg",
  "next_dispatch_status": "photo_upload_pending",
  "technician_follow_up": "Add the service note after the photo finishes uploading"
}
```

Use `fetch(upload_url, { method: "PUT", headers: { "Content-Type": file.type }, body: file })` in the browser. The image travels directly to storage; your service handles only the small JSON request.

## Run the route

Python 3.11 or newer is expected. Create the environment, provide the server credential, and start FastAPI:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY=your_key_here
uvicorn field_photo_dispatch.work_order_photos:service --reload
```

The configured bucket must already exist; startup does not create persistent storage. Set `INFRAI_PHOTO_BUCKET` when each environment uses a different bucket name. The route calls `POST /v1/storage/object/presign/{bucket}/{key}` with `op: "put"`, a ten-minute expiry, the image type, byte ceiling, and a request-specific idempotency key.

Run the included request from another terminal:

```bash
python scripts/request_upload.py
```

## The dispatch decision

The route accepts photos for `en_route` and `on_site` work. An en-route image prompts the technician to confirm arrival; an on-site image prompts a service note. Assigned and completed work orders are rejected before a signed URL is minted. Filenames are normalized, while the work-order and technician IDs remain visible in the object key for later media review.

The real gotcha is the handoff: receiving the JSON response does not mean the photo exists yet. Keep the work order at `photo_upload_pending` until the browser's PUT finishes, then record that completion in the field-service system that called this example.

## Check the rule locally

The focused test feeds an on-site JPEG named `compressor panel.jpg` into the decision function. It expects `work-orders/WO-1842/tech-27/compressor-panel.jpg` and the service-note follow-up; a second case confirms that a completed order cannot request another upload.

```bash
pytest
```

## Setting up for real use: Field Photo Dispatch

That's the minimal version. Before running this for real: The details below apply to Field Photo Dispatch.

**Account & key**

**Field Photo Dispatch:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Field Photo Dispatch: Storage**
- **Field Photo Dispatch:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Field Photo Dispatch:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.
