"""MCP stdio adapter. The FastAPI service remains the only state owner."""
import json
import os
from typing import Literal
from uuid import UUID
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

API = os.getenv("WAYPOINT_API_URL", "http://127.0.0.1:8000").rstrip("/")
mcp = FastMCP("Waypoint", instructions="Warehouse simulation only. Inspect state, compare policies and present a plan before requesting approval. Call review_plan with approved=true only after the user explicitly approves that exact plan. Never describe simulation results as real-world guarantees.")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)


def api(method, path, **kwargs):
    token = os.getenv('WAYPOINT_ACCESS_TOKEN', '')
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    with httpx.Client(base_url=API, timeout=90, headers=headers) as client:
        response = client.request(method, path, **kwargs)
        if response.is_error:
            raise ValueError(f"Waypoint API {response.status_code}: {response.text}")
        return response.json()


@mcp.tool(annotations=READ)
def inspect_warehouse() -> dict:
    """Read orders, robot positions, active policy, metrics and simulated time."""
    return api("GET", "/api/workspace")


@mcp.tool(annotations=WRITE)
def advance_simulation(ticks: int = 6) -> dict:
    """Advance the sandbox by 1–60 ticks; each tick represents ten seconds."""
    return api("POST", "/api/advance", json={"ticks": ticks})


@mcp.tool(annotations=WRITE)
def set_aisle_closure(enabled: bool) -> dict:
    """Close or reopen the central aisle in the simulation and reroute robots."""
    return api("POST", "/api/incident", json={"enabled": enabled})


@mcp.tool(annotations=WRITE)
def propose_plan(objective: Literal["throughput", "on_time", "distance"] = "throughput") -> dict:
    """Run three counterfactual simulations and persist a plan awaiting review. Does not apply a policy."""
    return api("POST", "/api/plans", json={"objective": objective})


@mcp.tool(annotations=WRITE)
def review_plan(plan_id: str, approved: bool) -> dict:
    """Approve or reject a pending plan. Require explicit user approval of this plan before setting approved=true."""
    validated_id = str(UUID(plan_id))
    return api("POST", f"/api/plans/{validated_id}/decision", json={"approved": approved})


@mcp.tool(annotations=READ)
def list_plans() -> list[dict]:
    """Read the latest 50 plans, their measured comparisons and review decisions."""
    return api("GET", "/api/plans")


@mcp.resource("waypoint://warehouse")
def warehouse_resource() -> str:
    """Current warehouse state."""
    return json.dumps(inspect_warehouse(), indent=2)


@mcp.resource("waypoint://assumptions")
def assumptions() -> str:
    return "10 seconds per tick; one grid cell per tick; per-unit loading time; shortest paths around racks and closures. Independent robot motion: no collision, battery, congestion or human-traffic physics. Compare 3 policies over 180 ticks. Local single-operator prototype; no real equipment integration."


@mcp.prompt()
def investigate_warehouse() -> str:
    return "Inspect the warehouse and explain the current bottleneck using its metrics. Propose a throughput plan, compare all three policies, explain assumptions, and ask me to approve the exact plan ID before changing the simulation."


if __name__ == "__main__":
    mcp.run(transport="stdio")
