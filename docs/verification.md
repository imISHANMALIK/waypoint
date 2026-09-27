# Verification

Verified locally on 27 September 2026 with Python 3.12.14 and Node.js 25.9.0.

## Automated checks

- **24 tests passed**: grid routing with closures, full-wave completion, unique assignments, deterministic immutable comparisons, valid/invalid CSV imports, request bounds, cross-origin protection, approval and rejection, stale-plan prevention, restart recovery, export, hosted sign-in, secure session cookies, expiry/tampering, rate limiting, and concurrent updates.
- **Real MCP protocol test passed**: the SDK client launches the stdio server, lists six tools, inspects a separate API, creates and rejects a plan, and lists two resources and one prompt.
- **TypeScript and Vite production build passed.** Phaser contributes most of the JavaScript bundle; Vite emits an advisory large-chunk warning.

## Bounded stress test

The test starts a separate server and database with **250 orders**, then sends **1,000 mixed requests at 32 concurrent clients**. It does not target the user's live warehouse.

| Operation | Requests | Median | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Read workspace | 750 | 117.80 ms | 132.67 ms | 202.33 ms |
| Advance simulation | 200 | 121.29 ms | 135.88 ms | 144.37 ms |
| Compare policies | 50 | 127.13 ms | 138.39 ms | 141.49 ms |

All 1,000 requests returned HTTP 200. Aggregate throughput was **282.94 requests/second** over 3.53 seconds. No lost ticks, duplicate active assignments or order-count corruption occurred. An additional 16-way approval race produced exactly **one successful application and fifteen HTTP 409 conflicts**. An invalid CSV left the warehouse intact.

Full machine-readable evidence: [stress-report.json](stress-report.json). Reproduce with:

```bash
.venv/bin/python scripts/stress_test.py --requests 1000 --concurrency 32
```

These measurements describe a bounded local synthetic workload, not a production capacity guarantee. They exclude hosted network latency, paid model calls and multiple server workers.

## Browser checks

The Phaser floor rendered in the in-app browser. The Field guide opens via keyboard navigation, includes all five technology explanations and CSV instructions, and its glossary search returns matching terms. A narrow-screen inspection found an overflowing CSV example; its grid child now permits shrinking and horizontal scrolling within the example.

## Limits

The optional live language-model explanation has not been tested against a paid provider. Docker is packaged but not built locally. CI and hosted runtime status are verified separately after publishing. There is no collision physics, calibrated real warehouse telemetry, multi-tenant identity or multi-process coordination.
