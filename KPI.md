# Efficiency and optimization

Every number below is produced by `scripts/kpi.py`, which measures the running
system rather than quoting it. Detection is scored against `answer_key.json` —
a file the application itself never opens — and the cost figures come from the
planner's own simulator replayed under different strategies.

## Running the report

From the repository root:

```bash
.venv/bin/python -m scripts.kpi              # all four datasets
.venv/bin/python -m scripts.kpi full_week    # one dataset
```

Takes about 7 seconds for all four. No server needed, no network, no flags to
configure. Point it at any folder under `data/eog/history/` that has an answer
key and it reports that folder's truth — including a judging `test/` folder.

The report prints four sections: DETECTION, RESPONSE, FLEET, ENGINE.

---

## 1. Detection quality

Did we find the faults, and how much warning did we give?

| dataset | found | invented | precision | recall | alarm lag | warning given |
|---|---|---|---|---|---|---|
| `full_week` | 23 / 23 | 0 | 0.981 | 0.965 | +0 min | 4.6 h |
| `snapshot_2026-10-08T1200` | 13 / 13 | 0 | 0.990 | 0.943 | +15 min | 4.6 h |
| `snapshot_2026-10-09T0330` | 15 / 15 | 0 | 0.992 | 0.955 | +5 min | 4.6 h |
| `snapshot_2026-10-10T0900` | 21 / 21 | 0 | 0.981 | 0.963 | +0 min | 4.8 h |

**Found / invented** count whole events. **Precision and recall** are stricter:
at every 5-minute reading, was each asset correctly shown as faulty? A
prediction is counted from `alarm_unix` — when the console actually lit up — not
from the retroactively refined onset, because that is what an operator would
have seen. **Warning given** is the median hours remaining before an automatic
shut-in at the moment the alarm fired.

> The README quotes precision 0.984 / recall 0.935 from a 30-minute sampling
> cadence. This report samples every reading and starts predictions at the alarm.
> Both are honest; they answer slightly different questions.

### Where the residual error lives

Event detection is perfect — 23 of 23, none invented. The sub-1.0 scores are
entirely about *timing*, and the timing error is not spread evenly:

| fault type | n | alarm lag | end error |
|---|---|---|---|
| `pump_failure` | 13 | **+0 min** | **+0 min** |
| `pipeline_leak` | 5 | +5 min | +70 min |
| `pump_degradation` | 5 | **+130 min** | +0 min |

Nearly all the recall loss is degradation taking ~130 minutes to confirm.
Nearly all the precision loss is a leak staying flagged ~70 minutes past repair.

**This is the most important thing to understand in the whole report.**
Degradation has no countdown — a worn pump still moves water, so the
recommendation is "schedule an inspection." A 130-minute delay there changes no
decision and costs no money. The fault that *does* carry a shutdown clock and
lost revenue, `pump_failure`, is detected with **zero lag and zero end error**.

The error concentrates where it is cheapest, and not by tuning. A pump failure
is a step change in flow; degradation ramps slowly, so the CUSUM chart needs
time to accumulate evidence before it can claim anything. The physics of each
fault sets its own detectability, and the economics happen to line up with it.

---

## 2. Response cost

What the recommended plans cost, against three alternatives.

| dataset | do nothing | greedy | **ours** | answer key | avoided | trucks used |
|---|---|---|---|---|---|---|
| `snapshot_2026-10-08T1200` | $12,120 | $5,109 | **$3,106** | $3,108 | $9,013 | 2 / 2 |
| `snapshot_2026-10-09T0330` | $7,549 | $1,810 | **$1,810** | $1,810 | $5,739 | 2 / 2 |
| `snapshot_2026-10-10T0900` | $11,901 | $3,022 | **$3,022** | $3,095 | $8,879 | 2 / 2 |

`full_week` has no pump failure live at its final timestamp, so there is nothing
to cost there. That is correct, not a gap.

**Do nothing** lets every tank reach its limit and shut its wells in
automatically — the cost of having no system at all. **Greedy** is a real
heuristic, not a strawman: the tank closest to its limit picks its own cheapest
plan first, and later tanks take whatever trucks remain. **Ours** searches
combinations across the shared fleet. **Answer key** is the challenge's own
reference plan where it states a price.

Three readings, strongest last:

- **74% cheaper than doing nothing** ($12,120 → $3,106). This is the headline,
  but it is the easiest bar to clear.
- **39% cheaper than greedy** ($5,109 → $3,106). This is the one that shows the
  search is doing work. First-come-first-served on a shared fleet leaves about
  $2,000 on the table at a single snapshot, because the first tank to grab a
  truck is not always the tank that needed it most.
- **At or below the reference plan everywhere**, including $73 *under* on
  `snapshot_2026-10-10T0900`.

---

## 3. Fleet sizing

The smallest yard that buys everything a larger one would.

| dataset | system | owned | needed | cost at owned | cost at needed | verdict |
|---|---|---|---|---|---|---|
| `snapshot_2026-10-08T1200` | S2 | 2 | 3 | $3,106 | $2,715 | short 1 ($391) |
| `snapshot_2026-10-09T0330` | S4 | 2 | 2 | $1,810 | $1,810 | right-sized |
| `snapshot_2026-10-10T0900` | S4 | 2 | 3 | $3,022 | $2,756 | short 1 ($266) |

This re-solves each system against a hypothetical fleet size using the same
allocator, so the curve is what the system would genuinely cost — not a
per-tank best case that quietly double-books one truck across three tanks.

**Needed** is where the cost curve flattens; past that point another truck buys
nothing. S2 and S4 are each one truck short at their worst snapshots, and the
table prices the gap. This is an operational recommendation, not a defect —
but it does mean the plans are optimal *given a constraint that is itself
suboptimal*.

---

## 4. Engine efficiency

| dataset | rows | parse | detect sweep | frame (cold) | frame (cached) | rows/sec |
|---|---|---|---|---|---|---|
| `full_week` | 393,120 | 0.62 s | 0.10 s | 1.2 ms | ~0 ms | 632,556 |
| `snapshot_2026-10-08T1200` | 196,755 | 0.31 s | 0.05 s | 0.1 ms | ~0 ms | 635,756 |
| `snapshot_2026-10-09T0330` | 233,025 | 0.39 s | 0.06 s | 1.5 ms | ~0 ms | 597,820 |
| `snapshot_2026-10-10T0900` | 302,055 | 0.46 s | 0.08 s | 1.4 ms | ~0 ms | 652,507 |

Memory is 99 MB for `full_week`, 346 MB peak with all four datasets resident.

### Why it is fast

The structural decision is the whole story: **a 22 MB telemetry file is read
exactly once per dataset, ever.**

`telemetry.csv` arrives in long format — one row per asset, metric and
timestamp. It is streamed into `{(asset_id, metric): Series}`, where each
`Series` holds parallel timestamp and value arrays. That shape is chosen for
how it gets used: detectors sweep a channel linearly, and the dashboard needs
"value as of time *t*", which is a `bisect` in O(log n).

Detection then runs **once over the entire recording**, not once per request.
Because the detectors are causal — the statistic at time *t* uses only data up
to *t* — replaying any timestamp is a filter over events already found, not a
re-analysis. That is the difference between a 1.2 ms replay frame and a 700 ms
one, and it is why the timeline can be scrubbed and played at all.

Over HTTP a frame costs **9 ms** uncached and **2.3 ms** cached — roughly a
112 fps ceiling, which is why timeline playback needed no batching endpoint,
no prefetch, and no streaming protocol. Plain per-frame fetching is already an
order of magnitude faster than it needs to be.

Two things that look like waste and are not: the per-channel exact-lookup
dictionaries cost 14 MB but the detectors genuinely use them, and the replay
cache grows ~7 KB per frame — a full playback pass over the week adds about
13 MB.

---

## 5. Why the optimization is provably optimal here

"Beats the alternatives" is not the same as "optimal." The stronger claim holds
on this data, and it is worth stating precisely because it is conditional.

**Per facility**, the plan search is exhaustive: every truck count × trip
count × subset of wells to shut in, with a bisection finding the latest moment a
shut-in can safely start. Nothing is approximated.

**Across facilities**, the allocator shortlists each facility to its cheapest
plan per truck-count before searching combinations. That filter could in
principle discard something useful — but only in one specific case: when a
*more expensive* plan using the same number of trucks releases them *earlier*,
letting another tank use them sooner.

That requires a truck to finish one job and reach a second tank inside a repair
window. On all four datasets, `reuse_possible` is **False** — no truck can. So
release timing can never affect another facility, the dominance filter discards
nothing that could have helped, and the combination search is exhaustive.

The secondary `keep=8` truncation never binds either: with a fleet of 2, there
are only three possible truck-count levels (0, 1, 2) to keep.

**Both approximations collapse on this data, so the allocation is globally
optimal within the cost model.**

---

## 6. How to interpret all of this

**Optimal within the model is not optimal in reality.** The plan assumes inflow
holds at its current rate, repairs take exactly the expected hours, and trucks
arrive on schedule. The countdown is reported as a p10/p50/p90 band, but the
plan is chosen against the median — there is no explicit safety margin for a
truck running late.

**The optimality proof is data-dependent.** It rests on `reuse_possible` being
false. On a denser network with shorter travel times the dominance filter
becomes lossy and the result drops back to near-optimal. The scheduler already
handles reuse correctly; the shortlist would need truck-release time added to
its dominance key to stay exact.

**Precision and recall are not the operational metric.** As section 1 shows,
identical-looking scores can mean very different things depending on which fault
type the error sits in. Read the per-category breakdown before the aggregate.

**Zero invented events is the number to trust least on unseen data.** It is
strong across 23 real events, but the `MIN_SHIFT_SIGMA = 2.0` floor that
produces it was chosen after measuring noise-versus-fault separation on these
same datasets. The separation was wide — noise episodes averaged ≤1.17σ and
real faults ≥11.6σ — so the threshold is not finely tuned to the answer key.
But four labelled datasets is four, and the honest claim is "no false positives
observed," not "no false positives possible."

**What would change these numbers.** A dataset with faster truck cycles would
weaken the optimality proof. A dataset with more simultaneous failures per
system would widen the gap between greedy and the allocator. A noisier sensor
baseline would raise the degradation alarm lag further, which still costs
nothing, and would be the first place to look if precision fell.
