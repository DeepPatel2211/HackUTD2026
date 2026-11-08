# NightShift AI

Oilfield operations dashboard and Python decision-support API for the EOG challenge. All actions are recommendations and simulations; nothing controls real equipment.

## Run locally

Requires Python 3.10+ and Node.js 20.9+.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m uvicorn backend.main:app --reload --port 8000
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. API documentation: http://localhost:8000/docs. If the local nvm shim reports no selected version, use the installed Node directory in PATH: `$env:Path = 'C:\Program Files\nodejs;' + $env:Path`.

The default snapshot has an ongoing pump failure. Switch datasets or scrub the replay timeline to investigate other incidents. The application reads only `network.json`, `ops.json`, and `telemetry.csv`. Add an unfamiliar dataset folder under `data/eog`, restart the backend, and select it in the dashboard. Inputs must conform to the included EOG schema. Dataset objects are cached; restart after replacing file contents.

## Features

- Dynamic network visualization, system filtering, facility investigation and recorded tank trends.
- Pump-fault detection; sustained running-flow mismatch for leaks; sustained underperformance for degradation. Normal stopped pump cycles do not trigger failure alerts.
- Fault-onset tracking, remaining repair horizon, telemetry-derived countdown, and lost oil/gas revenue.
- Event-based tank simulation with timed well shut-in, truck arrivals, return occupancy, automatic safety trip, and per-trip costs.
- Joint fleet allocation across concurrent failures in each system; alternatives, cost savings and simulated tank traces.
- Shift handoff, JSON event export, historical replay and responsive layout.
- Server-side Nemotron investigation with real tool calls for evidence, deterministic plans and verification. Missing credentials produce an explicit unavailable message.

## Nemotron

Set `NVIDIA_API_KEY` in the terminal running the backend. Optionally set `NVIDIA_MODEL` to a tool-capable NVIDIA-hosted Nemotron model available to your account. `.env.example` documents variables; the server does not automatically load `.env`. Credentials never reach browser code. The live endpoint/model must be validated against your NVIDIA account; offline operation never claims AI execution.

```powershell
$env:NVIDIA_API_KEY = 'your-key'
.venv/Scripts/python.exe -m uvicorn backend.main:app --reload
```

## Verification

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m scripts.validate_history
cd frontend
npm run typecheck
npm run build
```

Answer keys are opened only by offline validation and tests. EVENT_9 is checked by replaying its onset and asserting the calculated one-truck $905 plan; the application does not contain that event's answer.

The default model is documented in the [NVIDIA model catalog](https://build.nvidia.com/nvidia/llama-3_3-nemotron-super-49b-v1_5).

## Current limits

This is a local MVP, not a certified control system. The planner searches simultaneous first dispatches, equal trip counts per dispatched truck, and a common shut-in time for each selected well subset. It chooses the lowest-cost verified candidate across shared fleet allocations, conservatively reserving trucks across facilities for the horizon. It does not search sequential reuse between facilities, separate well shut-in times, or every possible dispatch schedule; global optimality is not claimed. The simulation uses current measured well water rates held constant and the specified fixed repair duration. An already tripped facility remains shut until repair even if a truck drains it.

Leak and degradation detection use fixed thresholds and the latest 12 running samples within a 24-hour window; reported onset for those categories is the earliest qualifying reading in that window, not a reconstructed historical onset. Confidence is a rule score, not a calibrated probability. Event export contains currently active detections rather than a complete resolved-event history. Inspection costs are not modeled. Marking a plan reviewed is temporary browser state. Dataset loading assumes complete EOG sensor series; malformed input can require correction before analysis. No authentication, persistent dispatch ledger or hosted deployment is included.

The included EOG data README requests Comic Sans typography and an Avon Corps copyright footer; both are reflected in the dashboard.
