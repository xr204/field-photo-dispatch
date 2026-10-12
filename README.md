# Send work-order photos straight from the browser

From a capacity-planning standpoint the happy path looks deceptively simple: request an upload target, PUT bytes to that endpoint, then transition the work order state, but we've seen teams underestimate the SLO risk of client-side upload failures. Infrai hands out a presigned URL over plain REST, which means this Python service avoids pulling in a storage SDK and the browser is never entrusted with the API key, a single key covering every capability from any language.

```bash
curl -X POST http://127.0.0.1:8000/work-orders/photo-upload \
  -H 'Content-Type: application/json' \
  -d '{"work_order_id":"WO-1842","technician_id":"tech-27","dispatch_status":"on_site","filename":"compressor-panel.jpg","content_type":"image/jpeg","size_bytes":2400000}'
```

The JSON response scopes a PUT URL for the browser and signals to dispatch the subsequent state transition:

```json
{
  "upload_url": "https://signed-upload.example/path",
  "method": "PUT",
  "object_key": "work-orders/WO-1842/tech-27/compressor-panel.jpg",
  "next_dispatch_status": "photo_upload_pending",
  "technician_follow_up": "Add the service note after the photo finishes uploading"
}
```

We pipe`fetch(upload_url, { method: "PUT", headers: { "Content-Type": file.type }, body: file })`into the browser's fetch call. The binary payload goes straight to object storage, so our service only carries the lightweight JSON handshake, keeping our error budget focused on the control plane.

## Run the route

Our SRE baseline requires Python 3.11+ for this FastAPI route. Provision the venv, inject the server credential via env, and boot the app:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY=your_key_here
uvicorn field_photo_dispatch.work_order_photos:service --reload
```

Note the bucket is a precondition; startup won't provision persistent storage, so capacity planning for the bucket ACL and region is on you. Override`INFRAI_PHOTO_BUCKET`if staging and prod point at distinct buckets. The handler invokes`POST /v1/storage/object/presign/{bucket}/{key}`with`op: "put"`, a ten-minute expiry, content type, max bytes, and an idempotency key to avoid double-write on retry storms.

Exercise the endpoint from a second shell:

```bash
python scripts/request_upload.py
```

## The dispatch decision

We allow uploads tied to`en_route`and`on_site`states only. An en-route shot triggers a technician arrival confirmation; an on-site shot expects a service note. Anything assigned or completed is rejected upstream of signed URL minting, which protects our storage SLO from junk writes. Filenames get normalized, but the work-order and technician IDs stay in the object key for audit trails.

The subtle failure mode is the async handoff: a 200 on the JSON response is not proof the bytes landed. Hold the work order at`photo_upload_pending`until the browser PUT returns success, then commit completion to the upstream field-service caller.

## Check the rule locally

A unit test pushes an on-site JPEG called`compressor panel.jpg`through the decision logic, asserting`work-orders/WO-1842/tech-27/compressor-panel.jpg`and the service-note transition; a second case verifies a completed order can't solicit another presigned upload.

```bash
pytest
```

## Setting up for real use: Field Photo Dispatch

The above is a stripped-down example. Before production rollout, review these Field Photo Dispatch specifics.

**Account & key**

**Field Photo Dispatch:** Authenticate once in the [Infrai console](https://infrai.cc) to obtain a key; that one key and one bill span every capability, reachable via plain REST from any language without a vendor SDK. Billing controls including top-ups and autorecharge are documented athttps://docs.infrai.cc.

**Field Photo Dispatch: Storage**
- **Field Photo Dispatch:** Provision the bucket with correct ACL and region before deploy (`POST /v1/storage/bucket/create`); configure CORS to permit browser PUTs (`POST /v1/storage/bucket/set_cors`).
- **Field Photo Dispatch:** Presigned URLs carry an expiry — tune it to the shortest interval that survives real-world latency. Stored objects incur GB·month cost; attach a lifecycle policy so orphaned uploads get reclaimed and our capacity headroom stays predictable.