"""Label-blocked inference and final-action replay audit; no EOG files are changed.

Run: python -m scripts.audit_eog_runtime [history/dataset_name ...]
Checks recording endpoints, hourly frames, and detected alarm/end boundaries.
This verifies feasibility/consistency, not optimality against an unseen answer key.
"""
from __future__ import annotations

import builtins
import json
import sys
from pathlib import Path
from unittest.mock import patch

from backend.engine import Analysis
from backend.planner import FacilityProblem


def audit(name):
    opened = set()
    original = builtins.open

    def guard(file, *args, **kwargs):
        if not isinstance(file, int):
            path = Path(file)
            if 'answer_key' in str(path):
                raise AssertionError('Inference tried to open an answer key')
            opened.add(path.name)
        return original(file, *args, **kwargs)

    with patch('builtins.open', guard), patch('io.open', guard), patch.object(Path, 'open', guard):
        analysis = Analysis(name)
        data = analysis.data
        stamps = {data.start, data.end, *range(data.start, data.end, 3600)}
        for event in analysis.events:
            stamps.add(event.alarm_unix)
            if event.end_unix is not None:
                stamps.update((event.end_unix - data.step, event.end_unix))
        checks = 0
        for now in sorted(stamps):
            view = analysis.at(now)
            usage = {}
            for alert in view['alerts']:
                plan = alert['recommendation']
                assert plan['verified'], (now, alert['facility_id'])
                if alert['category'] != 'pump_failure':
                    assert plan['actions'] == [{'type': 'field_inspection', 'asset_id': alert['asset_id']}]
                    continue
                facility = data.facilities[alert['facility_id']]
                water, revenue = analysis.well_rates(facility, view['now'])
                horizon = max(0, data.ops['expected_repair_hours']['pump_failure'] -
                              (view['now'] - alert['onset_unix']) / 3600)
                problem = FacilityProblem(data, facility,
                                          data.value(facility['tank']['id'], 'level_pct', view['now']),
                                          horizon, water, revenue, now=view['now'])
                wells = {well['id']: i for i, well in enumerate(facility['wells'])}
                starts, arrivals = {}, []
                for action in plan['actions']:
                    if action['type'] == 'shut_in_wells':
                        starts.update({wells[well]: action.get('start_after_min', 0) / 60
                                       for well in action['wells']})
                    elif action['type'] == 'dispatch_truck':
                        count, trips = action['trucks'], action['trips_per_truck']
                        delay = plan['dispatch_delay_min'] / 60
                        expected = [round(delay + problem.response_h + k * problem.cycle_h, 9)
                                    for k in range(trips)]
                        assert action['arrival_hours'] == expected
                        assert all(0 <= t < horizon for t in expected)
                        end = delay + problem.busy_hours(count, trips)
                        assert abs(action['busy_until_hour'] - end) < 1e-8
                        arrivals.extend(t for t in expected for _ in range(count))
                        # At equal times, release trucks before assigning the next job.
                        events = usage.setdefault(problem.system_id, [])
                        events.extend(((delay, count), (end, -count)))
                    else:
                        assert action['type'] == 'none'
                actual = problem.run(list(starts), starts, arrivals)
                assert actual is not None
                for key in ('cost', 'tripped', 'trace', 'verified'):
                    assert actual[key] == plan[key], (name, now, facility['id'], key)
                checks += 1
            for system, events in usage.items():
                active = 0
                for _, delta in sorted(events):
                    active += delta
                    assert 0 <= active <= data.ops['systems'][system]['emergency_fleet_size']
        assert opened == {'network.json', 'ops.json', 'telemetry.csv'}, opened
        result = {'dataset': name, 'frames_checked': len(stamps), 'pump_plans_replayed': checks,
                  'runtime_files_opened': sorted(opened), 'detected_events': len(analysis.events),
                  'end_alerts': [{key: alert[key] for key in ('facility_id', 'category', 'recommendation')}
                                 for alert in analysis.at(data.end)['alerts']],
                  'fleets': {key: value['emergency_fleet_size'] for key, value in data.ops['systems'].items()},
                  'trucking': data.ops['emergency_trucking'], 'repair_rules': data.ops['expected_repair_hours'],
                  'result': 'PASS'}
    return result


if __name__ == '__main__':
    names = sys.argv[1:] or ['history/mock_test_2026-10-10T1530']
    print(json.dumps([audit(name) for name in names], indent=2))
