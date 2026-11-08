"""Measured KPIs for the NightShift console.

    .venv/bin/python -m scripts.kpi            # every dataset
    .venv/bin/python -m scripts.kpi full_week  # just one

Four sections:

  DETECTION  how much of the truth we found, and how much warning we gave
  RESPONSE   what the planner's choices cost against the alternatives
  FLEET      whether each system's yard holds the right number of trucks
  ENGINE     wall-clock cost of loading and replaying a week of telemetry

Nothing here is asserted. Detection is scored against answer_key.json, which the
running app never opens; the cost figures come from the planner's own simulator
replayed under different strategies; the timings are measured on a cold load.
Point it at a new dataset folder and it reports that folder's truth.
"""
from __future__ import annotations

import json
import re
import resource
import sys
import time

from backend.dataset import ROOT, Dataset
from backend.detect import Baselines, detect_all
from backend.engine import Analysis, analyze, load
from backend.planner import FacilityProblem, allocate, candidates

FOLDERS = ['full_week', 'snapshot_2026-10-08T1200', 'snapshot_2026-10-09T0330',
           'snapshot_2026-10-10T0900']


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _key(folder: str) -> list[dict]:
    """The labels for a dataset. Only this script ever reads them."""
    return json.loads((ROOT / f'history/{folder}/answer_key.json').read_text())


def _spans(records: list[dict], end: int) -> dict[tuple[str, str], list[tuple[int, int]]]:
    """Group events into (facility, category) -> [(start, stop), ...].

    An event with no end is still running, so it runs to the end of the recording.
    """
    out: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for record in records:
        stop = record.get('end_unix') or end
        out.setdefault((record['facility'], record['category']), []).append(
            (record['onset_unix'], stop))
    return out


def _covered(spans, key, ts: int) -> bool:
    return any(lo <= ts <= hi for lo, hi in spans.get(key, []))


def _median(values: list[float]) -> float:
    return sorted(values)[len(values) // 2] if values else 0.0


def _rule(title: str) -> None:
    print(f'\n{title}')
    print('=' * len(title))


# --------------------------------------------------------------------------
# DETECTION -- did we find the truth, and how early?
# --------------------------------------------------------------------------

def _match(analysis, labels) -> tuple[int, int, list[float]]:
    """Pair detected events with labelled ones, by facility, kind and rough time.

    Returns (hits, invented, alarm latencies in minutes). A latency is measured
    from the labelled onset to the moment the console first raised the alarm --
    negative would mean we alarmed before the fault began, which cannot happen.
    """
    found, hits, latencies = list(analysis.events), 0, []
    for label in labels:
        match = next((e for e in found
                      if e.facility_id == label['facility']
                      and e.category == label['category']
                      and abs(e.onset_unix - label['onset_unix']) < 6 * 3600), None)
        if match is None:
            continue
        found.remove(match)
        hits += 1
        latencies.append((match.alarm_unix - label['onset_unix']) / 60.0)
    return hits, len(found), latencies


def _confusion(analysis, labels) -> tuple[int, int, int]:
    """Sample-level true/false positives, asset by asset, reading by reading.

    Event counts alone hide whether a fault was flagged for its whole life. This
    walks the recording and asks, at every timestamp, whether each asset was
    correctly shown as faulty. Predictions start at `alarm_unix`, not the
    refined onset, because that is when an operator would actually have seen it.
    """
    data = analysis.data
    truth = _spans(labels, data.end)
    predicted = _spans([{'facility': e.facility_id, 'category': e.category,
                         'onset_unix': e.alarm_unix, 'end_unix': e.end_unix}
                        for e in analysis.events], data.end)
    keys = set(truth) | set(predicted)
    tp = fp = fn = 0
    ts = data.start
    while ts <= data.end:
        for key in keys:
            actual, guess = _covered(truth, key, ts), _covered(predicted, key, ts)
            tp += actual and guess
            fp += guess and not actual
            fn += actual and not guess
        ts += data.step
    return tp, fp, fn


def _lead_times(folder: str, analysis) -> list[float]:
    """Hours of warning each pump failure bought, measured at the alarm.

    This is the number the challenge is really about: when the console lit up,
    how long did the operator still have before the tank forced a shut-in?
    """
    leads = []
    for event in analysis.events:
        if event.category != 'pump_failure':
            continue
        view = analyze(f'history/{folder}', event.alarm_unix)
        alert = next((a for a in view['alerts']
                      if a['facility_id'] == event.facility_id
                      and a['category'] == 'pump_failure'), None)
        if alert and alert.get('hours_to_limit') is not None:
            leads.append(alert['hours_to_limit'])
    return leads


def detection(folders: list[str]) -> None:
    _rule('DETECTION   scored against answer_key.json, which the app never loads')
    print(f'{"dataset":<28}{"found":>9}{"invented":>10}{"precision":>11}'
          f'{"recall":>9}{"alarm lag":>12}{"warning":>10}')
    for folder in folders:
        analysis = load(f'history/{folder}')
        labels = _key(folder)
        hits, invented, latencies = _match(analysis, labels)
        tp, fp, fn = _confusion(analysis, labels)
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 1.0
        leads = _lead_times(folder, analysis)
        print(f'{folder:<28}{hits:>4}/{len(labels):<4}{invented:>10}'
              f'{precision:>11.3f}{recall:>9.3f}'
              f'{_median(latencies):>+9.0f} min{_median(leads):>7.1f} h')
    print('\n  found/invented count whole events; precision and recall are per reading,')
    print('  per asset. "alarm lag" is onset to alarm; "warning" is median hours left')
    print('  before an automatic shut-in at the moment the alarm fired.')


# --------------------------------------------------------------------------
# RESPONSE -- what the chosen plans cost against the alternatives
# --------------------------------------------------------------------------

def _greedy(problems, options, fleet) -> list[dict]:
    """The obvious heuristic the allocator replaces.

    The tank closest to its limit picks its own cheapest plan first, and later
    tanks take whatever trucks are left. There is no lookahead, so a cheap early
    choice can strand a tank that needed the truck more. Every facility still
    ends up with a plan, because a do-nothing plan costs no trucks.
    """
    urgency = sorted(
        range(len(problems)),
        key=lambda i: (problems[i].limit - problems[i].initial)
        / max(1e-9, sum(problems[i].water) / 24.0))
    left, chosen = fleet, [None] * len(problems)
    for i in urgency:
        for plan in options[problems[i].facility_id]:
            if plan['trucks'] <= left:
                chosen[i] = plan
                left -= plan['trucks']
                break
    return chosen


def _reference_cost(labels) -> float:
    """The key writes its own plan's price into the text, e.g. "(~$1,298)"."""
    total = 0.0
    for label in labels:
        if label['status'] != 'ongoing' or label['category'] != 'pump_failure':
            continue
        price = re.search(r'~\$([\d,]+)', label.get('reference_action', ''))
        if price:
            total += float(price.group(1).replace(',', ''))
    return total


def response(folders: list[str]) -> None:
    _rule('RESPONSE    cost of the recommended plans at each dataset\'s "now"')
    print(f'{"dataset":<28}{"do nothing":>12}{"greedy":>11}{"ours":>10}'
          f'{"reference":>12}{"avoided":>11}{"trucks":>9}')
    for folder in folders:
        name = f'history/{folder}'
        analysis, view = load(name), analyze(f'history/{folder}')
        data = analysis.data
        failures = [a for a in view['alerts'] if a['category'] == 'pump_failure']
        if not failures:
            print(f'{folder:<28}{"-- no pump failure live at this timestamp --":>65}')
            continue

        by_system: dict[str, list[dict]] = {}
        for alert in failures:
            by_system.setdefault(alert['system_id'], []).append(alert)

        ours = nothing = greedy_cost = 0.0
        used = available = 0
        for system_id, group in by_system.items():
            problems, options = [], {}
            for alert in group:
                facility = data.facilities[alert['facility_id']]
                water, revenue = analysis.well_rates(facility, view['now'])
                problem = FacilityProblem(data, facility, alert['level_pct'],
                                          alert['repair_hours_remaining'],
                                          water, revenue)
                problems.append(problem)
                options[problem.facility_id] = candidates(problem)
            fleet = data.ops['systems'][system_id]['emergency_fleet_size']
            chosen = allocate(problems, options, fleet)
            ours += sum(plan['cost'] for plan in chosen)
            greedy_cost += sum(plan['cost'] for plan in _greedy(problems, options, fleet))
            nothing += sum(options[p.facility_id][0]['baseline_cost'] for p in problems)
            used += sum(plan['trucks'] for plan in chosen)
            available += fleet

        reference = _reference_cost(_key(folder))
        print(f'{folder:<28}'
              f'{f"${nothing:,.0f}":>12}'
              f'{f"${greedy_cost:,.0f}":>11}'
              f'{f"${ours:,.0f}":>10}'
              f'{(f"${reference:,.0f}" if reference else "--"):>12}'
              f'{f"${nothing - ours:,.0f}":>11}'
              f'{f"{used}/{available}":>9}')
    print('\n  "do nothing" lets every tank trip and shut its wells in automatically.')
    print('  "greedy" is first-come-first-served on the shared trucks; "ours" searches')
    print('  the combinations. "reference" is the answer key\'s own plan, where priced.')


# --------------------------------------------------------------------------
# FLEET -- is the yard the right size?
# --------------------------------------------------------------------------

def fleet(folders: list[str], max_trucks: int = 6) -> None:
    _rule('FLEET       smallest yard that buys everything a bigger one would')
    print(f'{"dataset":<28}{"system":>8}{"owned":>7}{"needed":>8}{"at owned":>11}'
          f'{"at needed":>12}{"verdict":>21}')
    for folder in folders:
        name = f'history/{folder}'
        analysis, view = load(name), analyze(name)
        data = analysis.data
        failures = [a for a in view['alerts'] if a['category'] == 'pump_failure']
        by_system: dict[str, list[dict]] = {}
        for alert in failures:
            by_system.setdefault(alert['system_id'], []).append(alert)
        if not by_system:
            continue
        for system_id, group in by_system.items():
            owned = data.ops['systems'][system_id]['emergency_fleet_size']
            curve = {}
            for size in range(0, max_trucks + 1):
                problems, options = [], {}
                for alert in group:
                    facility = data.facilities[alert['facility_id']]
                    water, revenue = analysis.well_rates(facility, view['now'])
                    problem = FacilityProblem(data, facility, alert['level_pct'],
                                              alert['repair_hours_remaining'],
                                              water, revenue)
                    problem.fleet = size
                    problems.append(problem)
                    options[problem.facility_id] = candidates(problem)
                curve[size] = sum(p['cost'] for p in allocate(problems, options, size))
            floor = min(curve.values())
            needed = next(size for size in sorted(curve) if curve[size] <= floor + 1e-6)
            at_owned = curve.get(owned, floor)
            gap = at_owned - curve[needed]
            verdict = (f'short {needed - owned} (${gap:,.0f})' if gap > 0.5
                       else f'{owned - needed} spare' if owned > needed
                       else 'right-sized')
            print(f'{folder:<28}{system_id:>8}{owned:>7}{needed:>8}'
                  f'{f"${at_owned:,.0f}":>11}{f"${curve[needed]:,.0f}":>12}'
                  f'{verdict:>21}')
    print('\n  "needed" is where the cost curve flattens: past it another truck buys')
    print('  nothing for this snapshot. A yard that is short shows what the gap costs.')


# --------------------------------------------------------------------------
# ENGINE -- what it costs to load and replay
# --------------------------------------------------------------------------

def engine(folders: list[str]) -> None:
    _rule('ENGINE      wall-clock cost of a cold load and a replay frame')
    print(f'{"dataset":<28}{"rows":>10}{"parse":>9}{"detect":>9}'
          f'{"frame cold":>12}{"frame warm":>12}{"rows/s":>11}')
    for folder in folders:
        path = ROOT / f'history/{folder}/telemetry.csv'
        rows = sum(1 for _ in path.open()) - 1

        start = time.perf_counter()
        data = Dataset(f'history/{folder}')
        parse = time.perf_counter() - start

        # Time the sweep on the dataset just parsed, rather than subtracting one
        # timing from another -- two separate parses differ enough to mislead.
        start = time.perf_counter()
        Baselines(data)
        detect_all(data)
        detect = time.perf_counter() - start

        fresh = Analysis(f'history/{folder}')   # uncached, for the frame timings

        stamps = [data.start + i * (data.end - data.start) // 12 for i in range(1, 12)]
        start = time.perf_counter()
        for ts in stamps:
            fresh.at(ts)
        cold = (time.perf_counter() - start) / len(stamps)
        start = time.perf_counter()
        for ts in stamps:
            fresh.at(ts)
        warm = (time.perf_counter() - start) / len(stamps)

        print(f'{folder:<28}{rows:>10,}{parse:>8.2f}s{detect:>8.2f}s'
              f'{cold * 1000:>10.1f}ms{warm * 1000:>10.2f}ms{rows / parse:>11,.0f}')

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak = peak / 1e6 if sys.platform == 'darwin' else peak / 1e3   # bytes vs KiB
    print(f'\n  peak resident memory across every dataset loaded above: {peak:,.0f} MB')
    print('  Detection sweeps a recording once; replay frames are then filters, which')
    print('  is why a frame costs milliseconds and a cached one costs nothing.')


def main() -> None:
    folders = sys.argv[1:] or FOLDERS
    unknown = [f for f in folders if not (ROOT / f'history/{f}').is_dir()]
    if unknown:
        raise SystemExit(f'No such dataset folder(s): {", ".join(unknown)}')
    print('NIGHTSHIFT KPI REPORT')
    detection(folders)
    response(folders)
    fleet(folders)
    engine(folders)
    print('\nScored offline against labelled history. Not a guarantee on unseen data.')


if __name__ == '__main__':
    main()
