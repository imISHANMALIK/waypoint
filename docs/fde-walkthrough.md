# FDE delivery walkthrough

## Customer problem

Fictional customer Acme Fulfillment wants to evaluate dispatch policies before changing operations. Order waves contain different shelf locations, priorities and deadlines. An aisle closure can increase travel. The operator needs a visible explanation and authority over the final decision.

## Discovery questions for a real engagement

- Which WMS owns orders, locations and deadlines?
- What matters most: throughput, SLA adherence, energy, labor or all four?
- Which actions may be simulated, suggested or automatically applied?
- What historical telemetry can calibrate robot speed and handling times?
- Who approves changes and how are outcomes audited?

## Implemented acceptance criteria

- Ingest the customer's agreed CSV schema with actionable errors and atomic failure.
- Observe robot assignments and movement in a game-engine scene.
- Inject and clear a route disruption without changing code.
- Compare multiple policies from identical initial conditions.
- Preserve evidence and approval state across restarts.
- Apply only a reviewed, non-stale plan; preserve in-flight assignments.
- Expose the same operations to an MCP-compatible assistant.
- Package local startup, dependency locks, tests, API docs and a container recipe.

## Demo script

1. Explain the order schema and load the sample. Start the simulation.
2. Select AMR-03, point to its order and changing position, then pause.
3. Close the central aisle. Show changed paths and the activity record.
4. Select “Maximize throughput” and run a comparison. Read the measured numbers; do not promise every snapshot improves.
5. Inspect the selected policy and alternative results. Reject one plan to demonstrate operator control.
6. Run a new comparison, approve it, resume playback, and show the policy in the footer.
7. Open Decision log and export the report.
8. In an MCP client, ask for inspection and a proposed plan. Require an explicit approval of its plan ID.

## Engineering tradeoffs to explain

- Python is authoritative; Phaser renders the same state instead of maintaining a separate simulation.
- Deterministic comparison is reproducible and measurable. Language models explain results rather than inventing operational parameters.
- LangGraph checkpoints allow long-lived approvals. SQLite is appropriate for this local single-operator pilot.
- A heuristic dispatch model is useful for demonstrating integration and decision workflows. It needs real data calibration, traffic physics and operational validation before it can guide a warehouse.
- MCP makes the business capabilities available through standard tools without making the assistant a second state owner.

## Delivery progression

This repository covers a local pilot from input file to simulation, recommendation, approval and output report. A customer deployment would next add authenticated connectors, historical replay, real telemetry, model calibration, evaluation datasets, process-level job coordination and staged operational rollout. Docker, CI and a free Render deployment recipe are included. The hosted demo has a shared access-code gate and clearly labeled ephemeral storage. No real customer integration has been provisioned.
