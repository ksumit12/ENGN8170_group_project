# Red Shed Real-Time Service (Add-on)

This add-on service implements real-time boat state tracking and admin/report APIs without changing the existing Flask BLE system.

Run:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install fastapi uvicorn sqlalchemy pydantic reportlab
uvicorn rt_service.api:app --host 0.0.0.0 --port 9000
```

SSE stream at `/api/stream`. Post events to `/api/events/ingest`.




