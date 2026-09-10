import json
import os
import urllib.request

payload = {
    "work_order_id": "WO-1842",
    "technician_id": "tech-27",
    "dispatch_status": "on_site",
    "filename": "compressor-panel.jpg",
    "content_type": "image/jpeg",
    "size_bytes": 2_400_000,
}
request = urllib.request.Request(
    os.environ.get("FIELD_SERVICE_URL", "http://127.0.0.1:8000/work-orders/photo-upload"),
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request) as response:
    print(json.dumps(json.load(response), indent=2))
