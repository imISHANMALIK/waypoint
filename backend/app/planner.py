"""LangChain tools + durable LangGraph approval workflow."""
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import TypedDict
from langchain.tools import tool
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from .simulation import compare, metrics


@tool
def inspect_warehouse(snapshot: dict) -> dict:
    """Read operational metrics from a supplied warehouse snapshot."""
    return metrics(snapshot)


@tool
def simulate_policies(snapshot: dict) -> list[dict]:
    """Compare FIFO, nearest-pick and urgent-first policies over 30 simulated minutes."""
    return compare(snapshot)


class PlanState(TypedDict, total=False):
    snapshot: dict
    objective: str
    metrics: dict
    comparisons: list[dict]
    recommendation: str
    summary: str
    mode: str
    approved: bool
    status: str
    trace: list[dict]


def build_planner(directory):
    connection = sqlite3.connect(str(Path(directory)/"checkpoints.sqlite"), check_same_thread=False)
    saver = SqliteSaver(connection)

    def inspect(state):
        result = inspect_warehouse.invoke({"snapshot": state["snapshot"]})
        return {"metrics": result, "trace": [{"step": "Inspect", "detail": f'{result["total"]} orders · {result["active_robots"]} active robots'}]}

    def simulate(state):
        results = simulate_policies.invoke({"snapshot": state["snapshot"]})
        return {"comparisons": results, "trace": state["trace"]+[{"step": "Simulate", "detail": "3 policies · identical starting state · 30-minute horizon"}]}

    def recommend(state):
        objective = state["objective"]
        if objective == "on_time":
            score = lambda r: (r["on_time"] or 0, r["completed"], -r["additional_distance"])
        elif objective == "distance":
            # Distance efficiency, subject to completing at least as many as FIFO.
            baseline = state["comparisons"][0]["completed"]
            score = lambda r: (r["completed"] >= baseline, -r["additional_distance"], r["completed"])
        else:
            score = lambda r: (r["completed"], r["on_time"] or 0, -r["additional_distance"])
        best = max(state["comparisons"], key=score)
        baseline = next(r for r in state["comparisons"] if r["policy"] == state["snapshot"]["policy"])
        gain = best["newly_completed"]-baseline["newly_completed"]
        names = {"fifo": "First in, first out", "nearest": "Nearest pick", "priority": "Urgent first"}
        summary = (f'{names[best["policy"]]} completes {best["newly_completed"]} additional orders over the next 30 simulated minutes '
                   f'({gain:+d} versus the current policy). Projected on-time rate: {best["on_time"] if best["on_time"] is not None else 0}%. '
                   'In-flight assignments are preserved; the policy applies to new assignments.')
        mode = "deterministic"
        model_name = os.getenv("WAYPOINT_MODEL", "").strip()
        if model_name:
            try:
                from langchain.chat_models import init_chat_model
                from langchain_core.prompts import ChatPromptTemplate
                from langchain_core.output_parsers import StrOutputParser
                prompt = ChatPromptTemplate.from_messages([
                    ("system", "Explain the supplied warehouse simulation in 3 short sentences. Use only these facts. "
                     "Do not invent savings or claim real-world validity. Do not change the selected policy. "
                     "Mention projections and that approval is required."),
                    ("human", "{facts}")])
                model = init_chat_model(model_name, temperature=0, timeout=25, max_retries=0)
                summary = (prompt | model | StrOutputParser()).invoke({"facts": json.dumps({"selected": best, "baseline": baseline})})
                mode = "model"
            except Exception:
                logging.getLogger(__name__).warning("Model explanation unavailable; deterministic explanation retained.")
                mode = "fallback"
        return {"recommendation": best["policy"], "summary": summary, "mode": mode,
                "trace": state["trace"]+[{"step": "Recommend", "detail": f'{names[best["policy"]]} · objective: {objective}'}]}

    def approval(state):
        approved = interrupt({"policy": state["recommendation"], "summary": state["summary"]})
        return {"approved": bool(approved), "status": "approved" if approved else "rejected",
                "trace": state["trace"]+[{"step": "Review", "detail": "Approved by operator" if approved else "Rejected by operator"}]}

    graph = StateGraph(PlanState)
    graph.add_node("inspect", inspect)
    graph.add_node("simulate", simulate)
    graph.add_node("recommend", RunnableLambda(recommend))
    graph.add_node("approval", approval)
    graph.add_edge(START, "inspect")
    graph.add_edge("inspect", "simulate")
    graph.add_edge("simulate", "recommend")
    graph.add_edge("recommend", "approval")
    graph.add_edge("approval", END)
    return graph.compile(checkpointer=saver), connection
