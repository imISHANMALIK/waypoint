"""Deterministic, discrete warehouse model. One tick is ten simulated seconds.

Robots route around racks and closures. Robot-to-robot collisions, acceleration,
battery charging and human traffic are intentionally outside this planning model.
"""
from collections import deque
from copy import deepcopy
import random
from uuid import uuid4

WIDTH, HEIGHT = 25, 17
RACKS = [(x, y) for x in (4, 5, 8, 9, 14, 15, 18, 19) for y in (*range(3, 7), *range(10, 14))]
SHELVES = {f"{letter}{row + 1}": [x, y] for letter, x in zip("ABCD", (3, 7, 13, 17)) for row, y in enumerate((3, 5, 10, 12))}
DOCKS = [[22, 4], [22, 8], [22, 12]]
POLICIES = ("fifo", "nearest", "priority")


def route(start, end, blocked):
    """Breadth-first shortest path on a four-connected grid, excluding start."""
    start, end = tuple(start), tuple(end)
    walls = set(map(tuple, RACKS)) | set(map(tuple, blocked))
    queue, previous = deque([start]), {start: None}
    while queue:
        cell = queue.popleft()
        if cell == end:
            path = []
            while cell != start:
                path.append(list(cell))
                cell = previous[cell]
            return list(reversed(path))
        for nx, ny in ((cell[0]+1, cell[1]), (cell[0], cell[1]+1), (cell[0]-1, cell[1]), (cell[0], cell[1]-1)):
            point = (nx, ny)
            if 1 <= nx < WIDTH-1 and 1 <= ny < HEIGHT-1 and point not in walls and point not in previous:
                previous[point] = cell
                queue.append(point)
    return None


def make_order(order_id, shelf, priority, due_tick, units):
    return dict(id=order_id, shelf=shelf, priority=priority, due_tick=due_tick, units=units,
                status="queued", started_tick=None, completed_tick=None, robot=None)


def fresh(orders=None):
    rng = random.Random(18)
    if orders is None:
        shelves = list(SHELVES)
        orders = [make_order(f"ORD-{1041+i}", rng.choice(shelves), "urgent" if i % 5 == 0 else "standard",
                            65 + rng.randrange(140), rng.randrange(1, 5)) for i in range(48)]
    return dict(id=str(uuid4()), revision=0, tick=0, policy="fifo", blocked=[], incident=False,
                orders=orders, robots=[dict(id=f"AMR-{i+1:02}", pos=[2, 2+i*2], path=[],
                order=None, phase="idle", wait=0, distance=0) for i in range(6)],
                events=[dict(tick=0, kind="info", text=f"Wave loaded · {len(orders)} orders ready for dispatch")], history=[])


def event(state, text, kind="info"):
    state["events"].insert(0, dict(tick=state["tick"], kind=kind, text=text))
    state["events"] = state["events"][:60]


def metrics(state):
    done = [o for o in state["orders"] if o["status"] == "complete"]
    queued = [o for o in state["orders"] if o["status"] == "queued"]
    late = [o for o in state["orders"] if o["status"] != "complete" and o["due_tick"] < state["tick"]]
    on_time = sum(o["completed_tick"] <= o["due_tick"] for o in done)
    return dict(total=len(state["orders"]), completed=len(done), queued=len(queued),
                in_progress=sum(o["status"] == "picking" for o in state["orders"]), at_risk=len(late),
                on_time=round(100*on_time/len(done), 1) if done else None,
                throughput=round(len(done)*360/max(state["tick"], 1), 1),
                average_cycle=round(sum(o["completed_tick"]-o["started_tick"] for o in done)*10/len(done), 1) if done else None,
                distance=sum(r["distance"] for r in state["robots"]),
                active_robots=sum(r["phase"] != "idle" for r in state["robots"]))


def tick(state, count=1, record=True):
    order_map = {o["id"]: o for o in state["orders"]}
    for _ in range(count):
        state["tick"] += 1
        for robot in state["robots"]:
            if robot["phase"] == "idle":
                available = [o for o in state["orders"] if o["status"] == "queued"]
                if not available:
                    continue
                if state["policy"] == "fifo":
                    candidates = available
                else:
                    candidates = sorted(available, key=lambda o: (
                        (0 if o["priority"] == "urgent" else 1) if state["policy"] == "priority" else 0,
                        o["due_tick"] if state["policy"] == "priority" else 0,
                        abs(SHELVES[o["shelf"]][0]-robot["pos"][0])+abs(SHELVES[o["shelf"]][1]-robot["pos"][1])))
                for order in candidates:
                    path = route(robot["pos"], SHELVES[order["shelf"]], state["blocked"])
                    if path is not None:
                        robot.update(order=order["id"], path=path, phase="picking")
                        order.update(status="picking", started_tick=state["tick"], robot=robot["id"])
                        break
            if robot["path"]:
                robot["pos"] = robot["path"].pop(0)
                robot["distance"] += 1
            elif robot["phase"] == "picking":
                order = order_map[robot["order"]]
                robot.update(phase="loading", wait=order["units"]+2)
            elif robot["phase"] == "loading":
                robot["wait"] -= 1
                if robot["wait"] <= 0:
                    paths = [route(robot["pos"], dock, state["blocked"]) for dock in DOCKS]
                    paths = [p for p in paths if p is not None]
                    if paths:
                        robot.update(phase="delivering", path=min(paths, key=len))
            elif robot["phase"] == "delivering":
                order = order_map[robot["order"]]
                order.update(status="complete", completed_tick=state["tick"])
                if record:
                    event(state, f'{robot["id"]} delivered {order["id"]}', "success")
                robot.update(order=None, phase="idle")
        if record and state["tick"] % 6 == 0:
            state["history"].append(dict(tick=state["tick"], **metrics(state)))
            state["history"] = state["history"][-120:]
    return state


def set_incident(state, enabled):
    state["incident"] = enabled
    state["blocked"] = [[12, y] for y in range(4, 13)] if enabled else []
    state["revision"] += 1
    for robot in state["robots"]:
        if robot["path"]:
            path = route(robot["pos"], robot["path"][-1], state["blocked"])
            if path is None:
                raise ValueError("Closure would make an active destination unreachable")
            robot["path"] = path
    event(state, "Central aisle closed · routes recalculated" if enabled else "Central aisle reopened", "warning" if enabled else "success")


def compare(state, horizon=180):
    """Counterfactuals from identical snapshots; no writes to the live world."""
    results = []
    before = metrics(state)
    for policy in POLICIES:
        world = deepcopy(state)
        world["policy"] = policy
        tick(world, horizon, record=False)
        result = metrics(world)
        results.append(dict(policy=policy, **result, newly_completed=result["completed"]-before["completed"],
                            additional_distance=result["distance"]-before["distance"]))
    return results
