# Waypoint

**See the floor. Shape the flow.** A complete local warehouse operations studio built with Phaser, FastAPI, LangChain, LangGraph, and an MCP server.

Import an order wave, watch six robots pick and dispatch goods, close an aisle, compare routing policies, approve a recommendation, and export the evidence. The default experience works without API keys. Optional language-model explanations sit on top of measured simulation results.

## Run it

This delivered checkout already has its dependencies and frontend build installed. From this folder:

```bash
./scripts/start.sh
```

Open **http://127.0.0.1:8000**. Interactive API docs: **http://127.0.0.1:8000/docs**. If the preview is already running, just open it; do not start a second server on the same port.

For a fresh checkout, install **Python 3.11–3.13**, **Node.js 22+**, and npm, then:

```bash
./scripts/setup.sh
./scripts/start.sh
```

`setup.sh` chooses a compatible Python automatically. You can override it with `PYTHON_BIN=/path/to/python3.12 ./scripts/setup.sh`. Setup also writes `mcp.local.json` with absolute paths for this checkout. Dependencies are locked in `backend/requirements.lock` and `frontend/package-lock.json`. Shell scripts target macOS/Linux.

## A five-minute walkthrough

1. **Run simulation.** The sample contains 48 orders, 6 robots, 16 pick locations and 3 dispatch bays. Try 4× speed and select a robot.
2. **Open Order waves.** Search an order, filter status, download the sample CSV or import your own. Import replaces the current wave and resets its clock.
3. **Close the central aisle.** Active paths reroute around the closure. Reopen it to restore the original layout.
4. **Find a better flow.** Choose throughput, on-time delivery or distance. The planner pauses UI playback, clones the current state, and simulates FIFO, nearest-pick and urgent-first for 180 ticks each.
5. **Review the evidence.** Approve or reject the pending plan. Approval changes new assignments only; active work continues. The decision log survives refreshes and backend restarts.
6. **Export report.** Download the full state, metrics, plan comparisons, traces, decisions and model assumptions as JSON.

## Where each component fits

| Component | Real responsibility | Main source |
| --- | --- | --- |
| Phaser 3.90 | Isometric scene, robot animation, selection, path overlay and zoom | `frontend/src/Warehouse.tsx` |
| React + TypeScript | Operations UI, CSV flow, metrics, plan approval and responsive layouts | `frontend/src/main.tsx` |
| FastAPI | Validation, simulation commands, persistence, reports and built frontend serving | `backend/app/main.py` |
| LangChain | Typed inspection/simulation tools, runnable recommendation step, optional model integration | `backend/app/planner.py` |
| LangGraph | Inspect → simulate → recommend → durable approval interrupt → resume | `backend/app/planner.py` |
| MCP | Six tools, two resources and an investigation prompt over stdio | `backend/mcp_server.py` |
| SQLite | Saved world, decision history and durable graph checkpoints | `backend/app/storage.py` |

The authoritative simulation runs in Python so UI and MCP clients share one model. Phaser renders and animates that model. LangChain tools and LangGraph execute in demo mode too; only the optional language-model explanation needs a provider.

## Connect your MCP client

Start the backend, then copy the `waypoint` entry from **`mcp.local.json`** into your MCP client's server configuration. Do not overwrite other server entries. Generate it again after moving the project:

```bash
.venv/bin/python scripts/mcp_config.py > mcp.local.json
```

Use the same generated entry in Antigravity **if your installed version supports stdio MCP server configuration**. No existing IDE settings have been changed automatically.

Tools:

- `inspect_warehouse()` — current orders, robots, policy and metrics.
- `advance_simulation(ticks=6)` — advance 1–60 ticks.
- `set_aisle_closure(enabled)` — toggle the central aisle closure.
- `propose_plan(objective="throughput")` — persist a comparison awaiting review.
- `review_plan(plan_id, approved)` — explicitly approve or reject a plan.
- `list_plans()` — read the latest 50 plans.

Resources: `waypoint://warehouse`, `waypoint://assumptions`. Prompt: `investigate_warehouse`.

Try: **“Inspect the warehouse, compare dispatch policies, and show me the plan before changing anything.”**

The MCP adapter calls FastAPI over loopback; it never opens the database directly. Keep stdout reserved for MCP messages. Configure `WAYPOINT_API_URL` if you change the backend port. The Python SDK is intentionally pinned to the maintained v1 API (`mcp<2`) used by this server.

## Optional model explanation

Copy `.env.example` to `.env`, set `WAYPOINT_MODEL` to a LangChain provider-qualified chat model identifier, and provide that provider's credentials. The OpenAI LangChain integration is installed; other providers require their integration package. Restart using `scripts/start.sh`, which reads `.env`.

The model sees only comparison metrics and the selected recommendation. It writes the explanation; it cannot choose an untested policy or bypass approval. If it times out or fails, the app retains the deterministic explanation and labels the fallback. No paid model call was used during verification. Model-generated wording has not been live-provider tested.

## CSV contract

```csv
order_id,shelf,priority,due_minutes,units
ORDER-001,A1,urgent,15,2
ORDER-002,D4,standard,30,3
```

- Exact headers, UTF-8, maximum 256 KB and 250 orders.
- Unique IDs: 1–40 letters/numbers/dashes/underscores.
- Shelves A1–A4, B1–B4, C1–C4, D1–D4.
- Priority: `standard` or `urgent`.
- Integer due time: 1–1440 minutes from wave start; units: 1–20.
- Invalid imports leave the existing state intact.

## Development and verification

```bash
# Terminal 1, from project root
.venv/bin/python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
# Terminal 2
npm --prefix frontend run dev
# Open http://127.0.0.1:5173

./scripts/check.sh
```

The Vite proxy sends `/api` traffic to FastAPI. The production build is served by FastAPI itself. `/docs` is on the backend port. Tests cover routing, order completion, immutable comparisons, import validation, stale approvals, rejection, restart recovery, report export, and a real MCP client/server handshake with a separate test API.

## Built-in manual and hosted mode

Open **Field guide** in the website sidebar for a complete beginner walkthrough, searchable glossary, CSV specification, component explanations, MCP setup and troubleshooting.

`render.yaml` defines a **free** Python web service. Render runs `scripts/render-build.sh` to install the Python dependencies and build the frontend, then serves both from FastAPI. Set `WAYPOINT_REQUIRE_AUTH=1`, a random `WAYPOINT_ACCESS_TOKEN` of at least 24 characters, and `WAYPOINT_EPHEMERAL=1`. The access code stays in Render environment variables; do not commit it. The website accepts it through a sign-in page. The MCP adapter accepts the same code through its private environment.

Free Render instances sleep when idle and cannot attach persistent disks. Their local SQLite data can disappear after restarts/redeploys. The website explains this and supports report export. This is a shared, access-controlled demo, not a multi-tenant production deployment.

Run the bounded stress test without touching your working warehouse:

```bash
.venv/bin/python scripts/stress_test.py --requests 1000 --concurrency 32
```

It starts and cleans up its own temporary API and database. Results are saved in `docs/stress-report.json`.

## Docker option

```bash
docker compose up --build
```

The app listens on loopback port 8000; SQLite files persist in `waypoint-data`. Stop the local preview before starting Docker on the same port. The Docker path is supplied for deployment; it has not been built in this environment. Use one API process/worker: the application lock and local SQLite design are for one operator. Never scale this image to multiple workers without redesigning concurrency and persistence.

## Honest scope

This is a working FDE portfolio prototype for a fictional customer. No real warehouse or robot is connected. One tick equals 10 simulated seconds; robots move one grid cell per tick, with per-order handling time. Shortest paths avoid racks and closures; robots move independently and do not simulate collisions, battery charging, acceleration or human traffic. Nearest-pick assignment uses Manhattan distance as a heuristic; actual movement uses breadth-first shortest paths. On-time percentage includes all completed orders; dispatch totals in plan comparisons count only new completions during the horizon. Throughput is completed orders divided by elapsed simulated time, not a rolling rate.

Plans are invalidated by a new wave, closure change or policy approval. Time advancement alone does not invalidate them; every plan records its snapshot time. SQLite stores only the latest workspace and up to 50 plans are shown/exported (older plans remain in the database). Run history persists locally. Hosted mode protects the workspace with a shared access code and signed, HttpOnly, eight-hour session cookies; MCP uses a bearer token. There is no per-user identity or tenancy. MCP approvals rely on the trusted local operator/client; this is not a security boundary against a malicious assistant.

For a real customer rollout, add identity and authorization, durable job workers, transactional multi-process storage, tenant boundaries, observability, realistic calibrated physics, WMS/robot adapters and an operational approval policy before exposing it beyond localhost.

See **[Architecture](docs/architecture.md)**, **[FDE delivery walkthrough](docs/fde-walkthrough.md)** and **[Verification](docs/verification.md)** for the implementation and demo details.

## Primary references

- [Phaser documentation](https://docs.phaser.io/)
- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [LangChain models](https://docs.langchain.com/oss/python/langchain/models)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
