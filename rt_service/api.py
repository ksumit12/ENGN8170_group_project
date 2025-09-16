from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, PlainTextResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import asyncio
import csv
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .db import init_db
from .models import BoatStatus, BoatStateEnum
from . import service
from . import schemas


app = FastAPI(title="RedShed Real-Time Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

init_db()


subscribers: List[asyncio.Queue] = []


def _broadcast(event: dict):
    for q in subscribers:
        q.put_nowait(event)


@app.get("/api/boats")
def list_boats(includeDeactivated: bool = Query(False)):
    boats = service.list_boats(include_deactivated=includeDeactivated)
    out: List[dict] = []
    with service.session_scope() as s:  # type: ignore
        for b in boats:
            last = service._latest_state_for_boat(s, b.id)
            out.append({
                "id": b.id,
                "boat_id": b.boat_id,
                "display_name": b.display_name,
                "status": b.status.value,
                "assigned_beacon_ids": service._csv_parse(b.assigned_beacon_ids),
                "last_state": last.state.value if last else None,
                "last_update": last.effective_at.isoformat() if last else None,
            })
    return out


@app.post("/api/boats", response_model=schemas.BoatOut)
def create_boat(payload: schemas.BoatCreate):
    boat = service.create_boat(payload.boat_id, payload.display_name, payload.assigned_beacon_ids)
    return schemas.BoatOut(
        id=boat.id, boat_id=boat.boat_id, display_name=boat.display_name, status=boat.status.value,
        assigned_beacon_ids=service._csv_parse(boat.assigned_beacon_ids)
    )


@app.patch("/api/boats/{boat_pk}", response_model=schemas.BoatOut)
def update_boat(boat_pk: int, payload: schemas.BoatUpdate):
    boat = service.update_boat(
        boat_pk,
        payload.display_name,
        BoatStatus(payload.status) if payload.status else None,
        payload.assigned_beacon_ids
    )
    if not boat:
        raise HTTPException(404, "Boat not found")
    return schemas.BoatOut(
        id=boat.id, boat_id=boat.boat_id, display_name=boat.display_name, status=boat.status.value,
        assigned_beacon_ids=service._csv_parse(boat.assigned_beacon_ids)
    )


@app.post("/api/events/ingest")
def ingest_event(payload: schemas.EventIngest):
    bs = service.ingest_event(payload.boat_id, service.BoatStateEnum(payload.new_state), payload.event_time)
    if bs:
        evt = {
            "type": "state_changed",
            "boat_id": payload.boat_id,
            "new_state": payload.new_state,
            "event_time": payload.event_time.astimezone(timezone.utc).isoformat(),
            "overdue": payload.new_state == "ON_WATER" and len(service.overdue_boats()) > 0 and payload.boat_id in service.overdue_boats(),
        }
        _broadcast(evt)
    return {"ok": True}


@app.get("/api/settings/closing-time")
def get_closing_time():
    return {"closing_time": service.get_closing_time()}


@app.patch("/api/settings/closing-time")
def set_closing_time(payload: dict):
    value = payload.get("closing_time")
    if not value:
        raise HTTPException(400, "closing_time is required")
    return {"closing_time": service.set_closing_time(value)}


@app.get("/api/stream")
async def sse_stream():
    async def event_generator(q: asyncio.Queue):
        try:
            while True:
                evt = await q.get()
                yield f"data: {JSONResponse(content=evt).body.decode()}\n\n"
        except asyncio.CancelledError:
            pass

    q: asyncio.Queue = asyncio.Queue()
    subscribers.append(q)
    return StreamingResponse(event_generator(q), media_type="text/event-stream")


@app.get("/api/overdue")
def get_overdue():
    return {"overdue_boat_ids": service.overdue_boats(), "closing_time": service.get_closing_time()}


# Simple dashboard for demo purposes
app.mount("/ui", StaticFiles(directory="rt_service/static", html=True), name="ui")

@app.get("/", response_class=HTMLResponse)
def root():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Red Shed Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-900 text-slate-100">
  <div class="max-w-6xl mx-auto p-4">
    <div class="flex items-center justify-between mb-4">
      <div class="text-2xl font-bold">Red Shed • Live Boats</div>
      <a class="px-3 py-2 bg-red-500 rounded text-white" href="/api/stream">SSE Stream</a>
    </div>
    <div id="overdue" class="hidden mb-4 p-3 rounded bg-red-700"></div>
    <div id="boats" class="grid md:grid-cols-2 lg:grid-cols-3 gap-3"></div>
  </div>
  <script>
    const boatsEl = document.getElementById('boats');
    const overdueEl = document.getElementById('overdue');

    function relTime(iso){
      if(!iso) return '—';
      const d = new Date(iso);
      const diff = Math.floor((Date.now()-d.getTime())/1000);
      if(diff<60) return diff+'s ago';
      if(diff<3600) return Math.floor(diff/60)+'m ago';
      return Math.floor(diff/3600)+'h ago';
    }

    async function refreshBoats(){
      const res = await fetch('/api/boats');
      const data = await res.json();
      boatsEl.innerHTML = data.map(b=>`
        <div class="bg-slate-800 rounded p-3">
          <div class="flex items-center justify-between">
            <div class="font-semibold">${b.display_name}</div>
            <span class="px-2 py-0.5 rounded text-xs ${b.last_state==='ON_WATER' ? 'bg-amber-500 text-black' : 'bg-emerald-500 text-black'}">${b.last_state || '—'}</span>
          </div>
          <div class="text-xs text-slate-300 mt-1">Last: ${new Date(b.last_update||'').toLocaleString()} (${relTime(b.last_update)})</div>
        </div>`).join('');
    }

    async function refreshOverdue(){
      const res = await fetch('/api/overdue');
      if(!res.ok) return;
      const d = await res.json();
      if(d.overdue_boat_ids && d.overdue_boat_ids.length){
        overdueEl.classList.remove('hidden');
        overdueEl.textContent = `Overdue after ${d.closing_time}: ` + d.overdue_boat_ids.join(', ');
      }else{ overdueEl.classList.add('hidden'); }
    }

    function startSSE(){
      const es = new EventSource('/api/stream');
      es.onmessage = (ev)=>{ try{ JSON.parse(ev.data); }catch{} refreshBoats(); refreshOverdue(); };
      es.onerror = ()=>{ setTimeout(startSSE, 5000); };
    }

    refreshBoats(); refreshOverdue(); startSSE();
    setInterval(()=>{refreshBoats(); refreshOverdue();}, 10000);
  </script>
</body>
</html>
"""


@app.get("/api/boats/{boat_pk}/history")
def get_history(boat_pk: int, from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None, page: int = 1, limit: int = 20):
    from_dt = datetime.fromisoformat(from_) if from_ else None
    to_dt = datetime.fromisoformat(to) if to else None
    rows, total = service.list_history(boat_pk, from_dt, to_dt, page, limit)
    out = {
        "total": total,
        "page": page,
        "limit": limit,
        "rows": [
            {
                "exit_time": r.exit_time.isoformat() if r.exit_time else None,
                "entry_time": r.entry_time.isoformat() if r.entry_time else None,
                "duration_seconds": r.total_duration,
            } for r in rows
        ]
    }
    return out


@app.get("/api/reports/usage")
def usage(from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None, boatId: Optional[str] = None):
    from_dt = datetime.fromisoformat(from_) if from_ else None
    to_dt = datetime.fromisoformat(to) if to else None
    rows = service.usage_summary(from_dt, to_dt, boatId)
    return [{"boat_id": bid, "total_outings": cnt, "total_minutes": mins} for bid, cnt, mins in rows]


@app.get("/api/reports/usage/export.csv")
def usage_csv(from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None, boatId: Optional[str] = None):
    from_dt = datetime.fromisoformat(from_) if from_ else None
    to_dt = datetime.fromisoformat(to) if to else None
    rows = service.usage_summary(from_dt, to_dt, boatId)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["boat_id", "total_outings", "total_minutes"]) 
    for bid, cnt, mins in rows:
        w.writerow([bid, cnt, mins])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv")


@app.get("/api/reports/usage/export.pdf")
def usage_pdf(from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None, boatId: Optional[str] = None):
    from_dt = datetime.fromisoformat(from_) if from_ else None
    to_dt = datetime.fromisoformat(to) if to else None
    rows = service.usage_summary(from_dt, to_dt, boatId)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "Red Shed Usage Report")
    y -= 30
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Range: {from_ or '-'} to {to or '-'}")
    y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Boat ID")
    c.drawString(180, y, "Outings")
    c.drawString(260, y, "Minutes")
    y -= 15
    c.setFont("Helvetica", 11)
    for bid, cnt, mins in rows:
        if y < 50:
            c.showPage(); y = height - 50; c.setFont("Helvetica", 11)
        c.drawString(40, y, bid)
        c.drawString(180, y, str(cnt))
        c.drawString(260, y, str(mins))
        y -= 14
    c.showPage()
    c.save()
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf")


