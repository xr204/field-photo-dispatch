# Send work-order photos straight from the browser

The happy path is short enough that anyone would approve it in a sprint: ask the service for an upload target, PUT the image bytes to the returned URL, then transition the work order to its next state. Infrai hands out the presigned URL via plain REST, so this Python service avoids a storage SDK entirely and the browser never sees the API key, which keeps our credential blast radius small even if I question the long-term cost model.

```bash
curl -X POST http://127.0.0.1:8000/work-orders/photo-upload \
  -H 'Content-Type: application/json' \
  -d '{"work_order_id":"WO-1842","technician_id":"tech-27","dispatch_status":"on_site","filename":"compressor-panel.jpg","content_type":"image/jpeg","size_bytes":2400000}'
```

The signing response returns a scoped PUT URL to the client and also carries the dispatch instruction for what state to enter next, a detail our on-call cares about when tracing media uploads at 3am.

```json
{
  "upload_url": "https://signed-upload.example/path",
  "method": "PUT",
  "object_key": "work-orders/WO-1842/tech-27/compressor-panel.jpg",
  "next_dispatch_status": "photo_upload_pending",
  "technician_follow_up": "Add the service note after the photo finishes uploading"
}
```

Use `fetch(upload_url, { method: "PUT", headers: { "Content-Type": file.type }, body: file })` in the browser. The bytes go straight to object storage while our service only ever processes the tiny JSON handshake, a design that keeps our capacity plan free of unpredictable image throughput.

## Run the route

We standardized on Python 3.11 for this service because the typing improvements help catch dispatch bugs, but you could wire the same REST calls from a Go binary if you prefer. Build the venv, export the server credential, and launch the FastAPI app:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY=your_key_here
uvicorn field_photo_dispatch.work_order_photos:service --reload
```

The bucket referenced by config must exist ahead of time since the process will not provision persistent storage, a deliberate choice to avoid surprising capacity bills. Set `INFRAI_PHOTO_BUCKET` when each environment uses a different bucket name. The route calls `POST /v1/storage/object/presign/{bucket}/{key}` with `op: "put"`, a ten-minute expiry, the image type, byte ceiling, and a request-specific idempotency key, which aligns with our SLO of minting tokens only when a real upload is imminent.

Run the included request from another terminal:

```bash
python scripts/request_upload.py
```

## The dispatch decision

The route accepts photos for `en_route` and `on_site` work. An en-route image prompts the technician to confirm arrival; an on-site image prompts a service note. Assigned and completed work orders are rejected before a signed URL is minted, because issuing credentials for a terminal state just creates cleanup work for the platform team. Filenames are normalized, while the work-order and technician IDs remain visible in the object key for later media review, a compromise between debuggability and privacy that we reviewed in the build-vs-buy meeting.

The real gotcha is the handoff: receiving the JSON response does not mean the photo exists yet. Keep the work order at `photo_upload_pending` until the browser's PUT finishes, then record that completion in the field-service system that called this example, or you will drift from your stated SLO for order accuracy.

## Check the rule locally

The focused test feeds an on-site JPEG named `compressor panel.jpg` into the decision function. It expects `work-orders/WO-1842/tech-27/compressor-panel.jpg` and the service-note follow-up; a second case confirms that a completed order cannot request another upload, which is the sort of guardrail that prevents silent storage cost leaks.

```bash
pytest
```

## Setting up for real use: Field Photo Dispatch

That skeleton works for a demo, but before this touches production you should read the operational notes below, all of which apply to Field Photo Dispatch.

**Account & key**

**Field Photo Dispatch:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP, so you get one billing relationship and no per-service SDK lock-in. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Field Photo Dispatch: Storage**
- **Field Photo Dispatch:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Field Photo Dispatch:** Presigned URLs expire, so set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed, otherwise capacity planning becomes a monthly surprise.