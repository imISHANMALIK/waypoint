from contextlib import asynccontextmanager
from datetime import datetime, timezone
import csv
import io
import json
import os
from pathlib import Path
import threading
import hmac
import time
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from fastapi.responses import Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from langgraph.types import Command
from .simulation import WIDTH, HEIGHT, RACKS, SHELVES, DOCKS, fresh, make_order, metrics, tick, set_incident, event
from .storage import Store
from .planner import build_planner
from .auth import SESSION_SECONDS, sign_session, valid_session

ROOT = Path(__file__).resolve().parents[2]
MAX_UPLOAD = 256_000


class Advance(BaseModel):
    ticks: int = Field(default=1, ge=1, le=60)


class Incident(BaseModel):
    enabled: bool


class PlanRequest(BaseModel):
    objective: Literal["throughput", "on_time", "distance"] = "throughput"


class Decision(BaseModel):
    approved: bool


class Login(BaseModel):
    access_code: str = Field(min_length=1, max_length=512)


def parse_orders(raw: bytes):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "Use a UTF-8 CSV file.")
    reader = csv.DictReader(io.StringIO(text))
    required = {"order_id", "shelf", "priority", "due_minutes", "units"}
    if not reader.fieldnames or set(reader.fieldnames) != required:
        raise HTTPException(422, "CSV headers must be: order_id,shelf,priority,due_minutes,units")
    orders, seen = [], set()
    try:
        for line, row in enumerate(reader, 2):
            if len(orders) >= 250:
                raise ValueError("Maximum 250 orders per wave")
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Row {line}: wrong number of columns")
            oid, shelf, priority = (row[k].strip() for k in ("order_id", "shelf", "priority"))
            if not oid or len(oid) > 40 or oid in seen or not all(c.isalnum() or c in "-_" for c in oid):
                raise ValueError(f"Row {line}: order_id must be unique, 1–40 letters, numbers, dashes or underscores")
            if shelf not in SHELVES:
                raise ValueError(f"Row {line}: unknown shelf {shelf}; use A1–D4")
            if priority not in ("standard", "urgent"):
                raise ValueError(f"Row {line}: priority must be standard or urgent")
            try:
                units, due = int(row["units"]), int(row["due_minutes"])
            except ValueError:
                raise ValueError(f"Row {line}: units and due_minutes must be integers")
            if not 1 <= units <= 20 or not 1 <= due <= 1440:
                raise ValueError(f"Row {line}: units must be 1–20 and due_minutes 1–1440")
            seen.add(oid)
            orders.append(make_order(oid, shelf, priority, due*6, units))
    except (ValueError, csv.Error) as exc:
        raise HTTPException(422, str(exc))
    if not orders:
        raise HTTPException(422, "CSV contains no orders")
    return orders


def create_app(data_dir=None):
    directory = Path(data_dir or os.getenv("WAYPOINT_DATA_DIR", str(ROOT/"data")))
    lock = threading.RLock()
    secret = os.getenv('WAYPOINT_ACCESS_TOKEN', '')
    if os.getenv('WAYPOINT_REQUIRE_AUTH') == '1' and len(secret) < 24:
        raise RuntimeError('Hosted mode requires WAYPOINT_ACCESS_TOKEN with at least 24 characters')
    attempts: dict[str, list[float]] = {}

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(directory)
        app.state.graph, app.state.checkpoint_connection = build_planner(directory)
        yield
        app.state.store.connection.close()
        app.state.checkpoint_connection.close()

    app = FastAPI(title="Waypoint API", version="1.0.0", lifespan=lifespan,
                  description="Warehouse simulation, durable planning approvals, and MCP integration.")

    @app.middleware("http")
    async def protect_local_writes(request, call_next):
        origin = request.headers.get("origin")
        allowed = {str(request.base_url).rstrip("/"), "http://localhost:5173", "http://127.0.0.1:5173"}
        public_origin = os.getenv('RENDER_EXTERNAL_URL', os.getenv('WAYPOINT_PUBLIC_ORIGIN', '')).rstrip('/')
        if public_origin:
            allowed.add(public_origin)
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin not in allowed:
            return JSONResponse({"detail": "Cross-origin writes are disabled"}, status_code=403)
        if request.method == 'POST':
            try:
                if int(request.headers.get('content-length', '0')) > 300_000:
                    return JSONResponse({'detail':'Request must be smaller than 300 KB'}, status_code=413)
            except ValueError:
                return JSONResponse({'detail':'Invalid content length'}, status_code=400)
        protected = request.url.path.startswith('/api/') and request.url.path not in ('/api/health', '/api/auth')
        if secret and protected:
            bearer = request.headers.get('authorization', '').removeprefix('Bearer ')
            if not (hmac.compare_digest(bearer.encode(), secret.encode()) or valid_session(request.cookies.get('waypoint_session', ''), secret)):
                return JSONResponse({'detail':'Sign in with the workspace access code'}, status_code=401)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.post('/api/auth')
    def login(body: Login, request: Request):
        if not secret:
            return {'authenticated':True}
        key = request.client.host if request.client else 'unknown'
        with lock:
            now = time.monotonic()
            recent = [stamp for stamp in attempts.get(key, []) if now-stamp < 60]
            if len(recent) >= 10:
                raise HTTPException(429, 'Too many attempts. Wait one minute before trying again.')
            if not hmac.compare_digest(body.access_code.encode(), secret.encode()):
                if len(attempts) >= 1024:
                    attempts.clear()
                attempts[key] = recent + [now]
                raise HTTPException(401, 'That access code is not correct')
            attempts.pop(key, None)
        response = JSONResponse({'authenticated':True})
        response.set_cookie('waypoint_session', sign_session(secret), max_age=SESSION_SECONDS,
                            httponly=True, secure=request.url.scheme == 'https' or os.getenv('RENDER_EXTERNAL_URL', '').startswith('https://'), samesite='strict', path='/')
        return response

    @app.post('/api/logout')
    def logout():
        response = JSONResponse({'authenticated':False})
        response.delete_cookie('waypoint_session', path='/')
        return response

    def public_state(state):
        return {**state, "metrics": metrics(state), "layout": {"width": WIDTH, "height": HEIGHT,
                "racks": RACKS, "shelves": SHELVES, "docks": DOCKS}}

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "1.0.0", "planner": "model" if os.getenv("WAYPOINT_MODEL") else "deterministic",
                "auth_required": bool(secret), "ephemeral_storage": os.getenv('WAYPOINT_EPHEMERAL') == '1'}

    @app.get("/api/workspace")
    def workspace():
        with lock:
            return public_state(app.state.store.load())

    @app.post("/api/advance")
    def advance(body: Advance):
        with lock:
            state = tick(app.state.store.load(), body.ticks)
            app.state.store.save(state)
            return public_state(state)

    @app.post("/api/reset")
    def reset():
        with lock:
            state = fresh()
            app.state.store.save(state)
            return public_state(state)

    @app.post("/api/incident")
    def incident(body: Incident):
        with lock:
            state = app.state.store.load()
            if state["incident"] != body.enabled:
                set_incident(state, body.enabled)
                app.state.store.save(state)
            return public_state(state)

    @app.post("/api/import")
    async def import_orders(file: UploadFile = File(...)):
        raw = await file.read(MAX_UPLOAD+1)
        await file.close()
        if len(raw) > MAX_UPLOAD:
            raise HTTPException(413, "CSV must be smaller than 256 KB")
        orders = parse_orders(raw)
        with lock:
            state = fresh(orders)
            app.state.store.save(state)
            return public_state(state)

    @app.get("/api/sample.csv")
    def sample():
        return Response((ROOT/"sample-data/orders.csv").read_text(), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="waypoint-orders.csv"'})

    @app.post("/api/plans")
    def plan(body: PlanRequest):
        with lock:
            snapshot = app.state.store.load()
            run_id = str(uuid4())
            result = app.state.graph.invoke({"snapshot": snapshot, "objective": body.objective},
                                            config={"configurable": {"thread_id": run_id}})
            run = {k: v for k, v in result.items() if k not in ("snapshot", "__interrupt__")}
            run.update(id=run_id, status="pending", created_at=datetime.now(timezone.utc).isoformat(),
                       workspace_id=snapshot["id"], revision=snapshot["revision"], based_on_tick=snapshot["tick"])
            app.state.store.save_run(run)
            return run

    @app.get("/api/plans")
    def plans():
        with lock:
            return app.state.store.runs()

    @app.post("/api/plans/{run_id}/decision")
    def decide(run_id: str, body: Decision):
        with lock:
            run = app.state.store.run(run_id)
            if run is None:
                raise HTTPException(404, "Plan not found")
            if run["status"] != "pending":
                raise HTTPException(409, "This plan has already been reviewed")
            state = app.state.store.load()
            if body.approved and (run["workspace_id"] != state["id"] or run["revision"] != state["revision"]):
                raise HTTPException(409, "The wave, aisle or policy changed. Generate a fresh plan.")
            config = {"configurable": {"thread_id": run_id}}
            saved = app.state.graph.get_state(config)
            # Recover a crash between graph resume and the atomic workspace/run write.
            if saved.next:
                result = app.state.graph.invoke(Command(resume=body.approved), config=config)
            else:
                result = saved.values
                if result.get("approved") != body.approved:
                    raise HTTPException(409, "An earlier decision is being recovered; retry that decision")
            run.update(status=result["status"], trace=result["trace"], decided_at=datetime.now(timezone.utc).isoformat())
            if body.approved:
                state["policy"] = run["recommendation"]
                state["revision"] += 1
                event(state, f'Operator approved {state["policy"]} dispatch policy', "success")
            else:
                event(state, "Plan rejected · current dispatch policy retained")
            app.state.store.commit_decision(state, run)
            return {"run": run, "workspace": public_state(state)}

    @app.get("/api/export")
    def export():
        with lock:
            report = {"exported_at": datetime.now(timezone.utc).isoformat(), "workspace": public_state(app.state.store.load()),
                      "plans": app.state.store.runs(), "model_assumptions": "10 seconds/tick; 1 cell/tick; independent robots; no collision or battery physics. Projections are simulation outputs."}
            return Response(json.dumps(report, indent=2), media_type="application/json",
                            headers={"Content-Disposition": 'attachment; filename="waypoint-report.json"'})

    dist = ROOT/"frontend/dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="console")
    return app


app = create_app()
