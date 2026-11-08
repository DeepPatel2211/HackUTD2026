# NightShift AI — EOG compliance audit

Audit date: 2026-11-08. Local working files were audited; no commit or push was made.
Previously modified frontend files were left untouched.

Official source: [SPEC.md](https://github.com/nihaal419/HackUTD-ZeroDay/blob/main/SPEC.md),
repository tree `135ba4c8348357457420a1111df80ec1906bcbdb`.
The local specification matches the downloaded official specification after newline normalization.

## Requirements

| # | Result | Evidence / qualification |
|---|---|---|
| 1 | PASS | Inspected local backend, loader, tests, validation scripts, API integration and official specification. |
| 2 | PASS within stated model | Removed the cheapest-per-truck shortlist and greedy scheduling from allocation. Joint mixed-integer optimization retains every feasible truck-count/trip-count option, independent well shut-in times and reusable vehicle assignments. A regression demonstrates a $250 feasible combined response that the former shortlist excluded. |
| 3 | PASS | Final serialized dispatch, arrival and well shut-in times are re-simulated. Returned cost, trip state, trace and verification come from that simulation. Vehicle intervals are checked for overlap. Replay audits checked 380 pump plans across 782 frames. |
| 4 | PASS | Already-tripped tanks remain latched, including below-limit sensor noise when all wells report shut. Repair-boundary trips and insufficient full loads are rejected. EVENT_6 returns zero cost and `none`. |
| 5 | PASS | All original 20 tests and 16 added regressions pass. Historical validation and all four KPI sections complete. Actual metrics and earlier failures appear below. |
| 6 | PASS | Mock inference passed with answer-key reads blocked: 177 frames, 106 pump-plan replays, only the three permitted input files opened. Custom IDs, capacity, limits, prices, fleet, travel and repair parameters are tested independently. |
| 7 | UNVERIFIED | The official recursive repository tree contains no `test/` folder. Its unseen recommendations cannot yet be checked. Existing folder-based dataset loading requires no application-code modification when those three-file datasets become available under `data/eog`. |
| 8 | PASS | SHA-256 comparison: all 23 EOG files unchanged. Runtime source contains no answer-key load; label-blocked inference also passed for all four historical datasets. Labels are read only by offline scoring/tests. |
| 9 | PASS for existing interfaces | Existing API tests pass, including events export, dataset discovery, fleet study, handoff and explicit Nemotron missing-credential behavior. No routes or response-field types were changed. Frontend and replay code were untouched. A live NVIDIA request was not made. |

## Correctness changes and limits

- Joint optimization uses SciPy/HiGHS instead of pruning each truck count to its cheapest individual plan. It can select a more expensive, shorter job to free a truck for another tank. Dispatch delays and individual well times are solved together, including waiting until a tank contains a full truck load.
- The old latest-start EDF feasibility assumption is false even for one truck. The compatibility checker now searches job orders; production allocation uses explicit vehicle assignments and non-overlap constraints instead.
- Public actions are serialized before verification. Arrival times, truck return times, dispatch delays, trajectories, trip status and costs describe the same final schedule. Late pickups cannot undo automatic shut-in.
- No-action is explicit; already-tripped facilities are not offered fictitious recovery plans. Trips exactly at repair are excluded from both counts and simulation.
- Fleet studies/KPIs use unrounded telemetry and remaining repair time and preserve the trip latch, matching dashboard planning inputs.
- Optimality is limited to **one simultaneous truck group per facility, equal trips per truck within that group, constant current measured inflow and the fixed repair duration in `ops.json`**. Mixed per-truck trip counts, multiple separate dispatch groups to the same facility and unrestricted field operations are not claimed optimal. No heuristic candidate-count cap is used; solver success is required. Large unseen instances may take longer; scalability is not established for an unavailable network.
- Numerical clearances: 0.000001 hours before repair for the last arrival; max(0.000001 bbl, capacity × 0.00000001) below tank shutdown. These are numerical tolerances, not an added operational safety policy.

## Commands actually executed

Commands use `.venv\Scripts\python.exe` on Windows.

| Command / stage | Actual result |
|---|---|
| `-m unittest discover -s tests -v`, baseline | 20/20 passed before changes. |
| `-m unittest discover -s tests -v`, final | 36/36 passed; final run 40.269 seconds while KPI checks ran concurrently. |
| `-m scripts.validate_history`, baseline and after optimizer fixes | Both completed successfully; results below. |
| `-m scripts.kpi`, initial | Failed with `ModuleNotFoundError: resource` on Windows. |
| `-m scripts.kpi`, final | All detection, response, fleet and engine sections completed; peak RSS explicitly unavailable on Windows. |
| `-m scripts.audit_eog_runtime` | Mock: 177 frames, 106 pump plans; PASS, answer-key access blocked. |
| `-m scripts.audit_eog_runtime history/full_week history/snapshot_2026-10-08T1200 history/snapshot_2026-10-09T0330 history/snapshot_2026-10-10T0900` | Historical: 605 frames, 274 pump plans; PASS, answer-key access blocked. |
| `-m pip check` | No broken requirements found. SciPy 1.15.3 installed and pinned. |
| `git diff --check` | Passed; Git emitted existing Windows line-ending warnings. |
| EOG before/after SHA-256 comparison | 23/23 files unchanged. |

An initial added label-access test failed because Python 3.10 pathlib caches its file opener;
the guard was corrected to intercept `Path.open` as well. Final tests pass. The test run
also emits a Starlette/httpx deprecation warning; it does not fail API verification.

### Historical validation results

Costs are rounded to whole dollars in the existing validation/KPI output.

| Dataset | Events found | Invented | Median alarm delay | Recommended cost / reference |
|---|---:|---:|---:|---:|
| full_week | 23/23 | 0 | 0 min | No pump failure active at recording end |
| October 8 noon | 13/13 | 0 | +15 min | $3,106 / $3,108 |
| October 9 03:30 | 15/15 | 0 | +5 min | $1,810 / $1,810 |
| October 10 09:00 | 21/21 | 0 | 0 min | $3,022 / $3,095 |

All three snapshot pump-alert orders match the offline key. Event matching is not
perfect sample-level detection: KPI precision/recall respectively are 0.981/0.965,
0.990/0.943, 0.992/0.955 and 0.981/0.963 in the table's dataset order.
Historical reference prices do not prove unrestricted optimization correctness.

At mock recording end, S5 Facility C and Facility D each receive one one-trip truck
at $905, total $1,810 from their shared two-truck fleet. Recommendations are physically
verified; no mock answer key was available or used to establish a reference optimum.

## Exact files changed by this audit

- `backend/planner.py`
- `backend/scheduling.py` (new)
- `backend/engine.py`
- `backend/main.py`
- `requirements.txt`
- `scripts/kpi.py`
- `scripts/audit_eog_runtime.py` (new)
- `tests/test_planner_compliance.py` (new)
- `README.md`
- `EOG_COMPLIANCE_AUDIT.md` (new)

Audit evidence files created:

- `artifacts/eog-audit/data-before.sha256.json`
- `artifacts/eog-audit/data-integrity.json`
- `artifacts/eog-audit/official-source.json`
- `artifacts/eog-audit/official-SPEC.md`
- `artifacts/eog-audit/tests.txt`
- `artifacts/eog-audit/history.txt`
- `artifacts/eog-audit/kpi.txt`
- `artifacts/eog-audit/mock-runtime.json`
- `artifacts/eog-audit/history-runtime.json`

## Remaining required work

When the official `test/` data is published, load its unmodified three-file folders
under `data/eog`, run the runtime audit and inspect the resulting recommendations.
That final unseen-network check remains pending. No unrestricted global-optimality
claim is made; the model limitations above remain explicit.
