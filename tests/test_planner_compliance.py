"""Small counterexamples and final-public-action checks, independent of labels."""
import builtins
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.dataset import Dataset
from backend.engine import Analysis, load
from backend.planner import FacilityProblem, _schedulable, allocate, candidates, reuse_possible, simulate


def problem(name, *, initial=80, horizon=6, water=(10,), revenue=(100,),
            response=0.5, cycle=1, capacity=100, limit=92, load_bbl=25, price=10, fleet=1,
            well_status=None):
    facility = {'id': name, 'tank': {'capacity_bbl': capacity},
                'wells': [{'id': f'{name}_W{i}'} for i in range(len(water))]}
    system = {'id': 'UNSEEN_SYSTEM'}
    ops = {'systems': {system['id']: {'emergency_fleet_size': fleet,
                                    'facilities': {name: {'response_min': response * 60,
                                                          'cycle_min': cycle * 60}}}},
           'emergency_trucking': {'truck_capacity_bbl': load_bbl, 'cost_per_trip': price}}
    data = SimpleNamespace(system_of={name: system}, ops=ops, limits={'shutdown': limit},
                           value=lambda *args: well_status)
    return FacilityProblem(data, facility, initial / capacity * 100, horizon,
                           [rate * 24 for rate in water], list(revenue),
                           now=0 if well_status is not None else None)


def replay_public(problem, plan):
    starts, arrivals = {}, []
    well_index = {w['id']: i for i, w in enumerate(problem.facility['wells'])}
    for action in plan['actions']:
        if action['type'] == 'dispatch_truck':
            arrivals.extend(t for t in action['arrival_hours'] for _ in range(action['trucks']))
        if action['type'] == 'shut_in_wells':
            starts.update({well_index[w]: action['start_after_min'] / 60 for w in action['wells']})
    return problem.run(list(starts), starts, arrivals)


class SharedFleetComplianceTests(unittest.TestCase):
    def test_more_expensive_shorter_job_enables_cheaper_system_solution(self):
        # A's individually cheapest truck plan makes two trips ($20), busy 2.5h.
        # That blocks B. A's $240 one-trip + shut-in plan returns at 1.5h,
        # allowing B's $10 trip. The former shortlist excluded this $250 solution.
        a = problem('NEW_A')
        b = problem('NEW_B', initial=70, horizon=3, revenue=(1000,), cycle=1.5)
        options = {p.facility_id: candidates(p) for p in (a, b)}
        self.assertEqual(min(p['cost'] for p in options['NEW_A'] if p['trucks'] == 1), 20)
        chosen = allocate([a, b], options, 1, keep=1)
        self.assertAlmostEqual(sum(p['cost'] for p in chosen), 250, places=2)
        self.assertEqual(chosen[0]['trips'], 1)
        self.assertEqual(chosen[1]['trips'], 1)
        self.assertGreaterEqual(chosen[1]['delay_h'] + 1e-7, chosen[0]['busy_h'])

    def test_final_arrivals_traces_costs_and_release_use_final_schedule(self):
        problems = [problem('A'), problem('B', initial=70, horizon=3,
                                           revenue=(1000,), cycle=1.5)]
        plans = allocate(problems, {p.facility_id: candidates(p) for p in problems}, 1)
        self.assertGreater(plans[1]['delay_h'], 0)
        for p, plan in zip(problems, plans):
            replay = replay_public(p, plan)
            self.assertIsNotNone(replay)
            self.assertEqual(plan['trace'], replay['trace'])
            self.assertEqual(plan['cost'], replay['cost'])
            self.assertEqual(plan['tripped'], replay['tripped'])
            self.assertTrue(plan['verified'])
            dispatch = next(a for a in plan['actions'] if a['type'] == 'dispatch_truck')
            self.assertAlmostEqual(dispatch['arrival_hours'][0], plan['delay_h'] + p.response_h)
            self.assertAlmostEqual(dispatch['busy_until_hour'], plan['delay_h'] + p.busy_hours(1, 1))

    def test_latest_start_edf_is_not_used_as_feasibility_proof(self):
        calls = _schedulable([('long', 1, 10, 1), ('short', 1, 1, 2)], 1)
        self.assertIsNotNone(calls)
        self.assertEqual(calls, {'short': 0, 'long': 1})

    def test_gang_dispatches_cannot_double_book_trucks(self):
        self.assertIsNone(_schedulable([('a', 2, 4, 0), ('b', 1, 1, 1)], 2))
        self.assertIsNotNone(_schedulable([('a', 2, 4, 0), ('b', 1, 1, 4)], 2))

    def test_independent_well_times_beat_common_subset_time(self):
        # Need to avoid 18 bbl. Cheap well avoids 12 for $60; expensive well
        # avoids the remaining 6 for $75. A common shut time costs at least $198.
        p = problem('X', initial=50, water=(2, 8), revenue=(10, 100), fleet=0)
        plan = allocate([p], {'X': candidates(p)}, 0)[0]
        self.assertAlmostEqual(plan['cost'], 135, places=2)
        starts = [a['start_after_min'] for a in plan['actions'] if a['type'] == 'shut_in_wells']
        self.assertEqual(len(set(starts)), 2)
        self.assertFalse(replay_public(p, plan)['tripped'])

    def test_dispatch_may_need_to_wait_for_a_full_load(self):
        p = problem('LOW', initial=0, horizon=3, water=(20,), response=0.1, limit=50, price=1)
        plan = allocate([p], {'LOW': candidates(p)}, 1)[0]
        self.assertEqual(plan['cost'], 1)
        self.assertGreaterEqual(plan['delay_h'], 1.15 - 1e-7)
        self.assertFalse(replay_public(p, plan)['tripped'])

    def test_no_truck_is_used_twice_at_the_same_time(self):
        ps = [problem('A'), problem('B', initial=70, horizon=3, revenue=(1000,), cycle=1.5)]
        plans = allocate(ps, {p.facility_id: candidates(p) for p in ps}, 1)
        intervals = sorted((a['arrival_hours'][0] - p.response_h, a['busy_until_hour'])
                           for p, plan in zip(ps, plans) for a in plan['actions']
                           if a['type'] == 'dispatch_truck')
        self.assertLessEqual(intervals[0][1], intervals[1][0] + 1e-7)

    def test_reuse_detection_does_not_mix_one_facility_response_with_another_cycle(self):
        data = SimpleNamespace(ops={'expected_repair_hours': {'pump_failure': 1},
            'systems': {'X': {'facilities': {'a': {'response_min': 1, 'cycle_min': 100},
                                          'b': {'response_min': 100, 'cycle_min': 1}}}}})
        self.assertFalse(reuse_possible(data))


class BoundaryComplianceTests(unittest.TestCase):
    def test_arrival_at_or_after_repair_is_illegal(self):
        for t in (-1, 6, 7):
            self.assertIsNone(simulate(100, 92, 80, 6, [240], [100], [], 6, [t], 20, 10))

    def test_max_trips_excludes_an_arrival_exactly_at_repair(self):
        p = problem('X', horizon=2.5)
        self.assertEqual(p.max_trips(), 2)
        self.assertEqual(len(p.arrivals(1, p.max_trips())), p.max_trips())

    def test_already_tripped_tank_stays_shut_even_if_drained(self):
        r = simulate(100, 92, 92, 6, [240], [100], [], 6, [1], 20, 10)
        self.assertTrue(r['tripped'])
        self.assertEqual(r['cost'], 610)
        self.assertEqual(r['trace'][-1]['level_pct'], 72)

    def test_shut_well_status_preserves_trip_latch_despite_level_noise(self):
        p = problem('X', initial=91.99, well_status=0)
        self.assertTrue(p.already_tripped)
        plan = candidates(p)[0]
        self.assertTrue(plan['tripped'])
        self.assertEqual(plan['cost'], 600)
        self.assertEqual(plan['actions'], [{'type': 'none'}])

    def test_repair_complete_and_safe_no_action(self):
        for p in (problem('DONE', horizon=0), problem('SAFE', initial=20, water=(1,))):
            plan = candidates(p)[0]
            self.assertEqual(plan['cost'], 0)
            self.assertEqual(plan['actions'], [{'type': 'none'}])

    def test_event_6_requires_no_action(self):
        # Labels are used only in this offline regression, never during inference.
        from backend.dataset import ROOT
        key = json.loads((ROOT / 'history/full_week/answer_key.json').read_text())
        event = next(e for e in key if e['id'] == 'EVENT_6')
        view = load('history/full_week').at(event['onset_unix'])
        alert = next(a for a in view['alerts'] if a['facility_id'] == event['facility'])
        self.assertEqual(alert['recommendation']['cost'], 0)
        self.assertEqual(alert['recommendation']['actions'], [{'type': 'none'}])
        self.assertFalse(alert['recommendation']['tripped'])


class RuntimeInputComplianceTests(unittest.TestCase):
    def test_mock_inference_cannot_open_any_answer_key(self):
        opened = []
        original = builtins.open

        def guard(file, *args, **kwargs):
            if not isinstance(file, int):
                name = str(file)
                if 'answer_key' in name:
                    raise AssertionError('Inference attempted to load labels')
                opened.append(Path(name).name)
            return original(file, *args, **kwargs)

        # Python 3.10's pathlib accessor caches io.open; intercept Path.open too.
        with patch('builtins.open', guard), patch('io.open', guard), patch.object(Path, 'open', guard):
            analysis = Analysis('history/mock_test_2026-10-10T1530')
            view = analysis.at(analysis.data.end)
        self.assertTrue(view['systems'])
        self.assertEqual(set(opened), {'network.json', 'ops.json', 'telemetry.csv'})

    def test_network_and_economics_are_not_bound_to_practice_ids(self):
        # A separate synthetic three-file fixture; official EOG files are untouched.
        network = {'defaults': {'tank_limits_pct': {'warning': 70, 'shutdown': 88}},
                   'systems': [{'id': 'CUSTOM_SYS', 'disposal_site': {'id': 'CUSTOM_D', 'pressure_psi': 1700},
                                'facilities': [{'id': 'CUSTOM_F', 'tank': {'id': 'CUSTOM_T', 'capacity_bbl': 1370},
                                                'pump': {'id': 'CUSTOM_P', 'max_flow_bpd': 9000},
                                                'pipeline': {'id': 'CUSTOM_L'},
                                                'wells': [{'id': 'CUSTOM_W', 'baseline_water_bpd': 480,
                                                           'oil_bpd': 13, 'gas_mcfd': 17}]}]}]}
        ops = {'prices': {'oil_per_bbl': 71, 'gas_per_mcf': 4},
               'expected_repair_hours': {'pump_failure': 7.25},
               'emergency_trucking': {'truck_capacity_bbl': 113, 'cost_per_trip': 321},
               'systems': {'CUSTOM_SYS': {'emergency_fleet_size': 4,
                                        'facilities': {'CUSTOM_F': {'response_min': 23, 'cycle_min': 47}}}}}
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'unseen'; folder.mkdir()
            (folder / 'network.json').write_text(json.dumps(network))
            (folder / 'ops.json').write_text(json.dumps(ops))
            (folder / 'telemetry.csv').write_text('timestamp,ts_unix,asset_id,metric,value\n'
                                                't0,123456,CUSTOM_T,level_pct,50\n'
                                                't1,123756,CUSTOM_T,level_pct,51\n')
            with patch('backend.dataset.ROOT', Path(tmp)):
                data = Dataset('unseen')
            facility = data.facilities['CUSTOM_F']
            p = FacilityProblem(data, facility, 51, data.ops['expected_repair_hours']['pump_failure'],
                                [480], [data.well_revenue_per_hour(facility['wells'][0])])
            self.assertEqual((data.start, data.end), (123456, 123756))
            self.assertEqual(p.system_id, 'CUSTOM_SYS')
            self.assertEqual(p.capacity, 1370)
            self.assertAlmostEqual(p.limit, 1370 * .88)
            self.assertEqual((p.fleet, p.load, p.trip_cost, p.horizon), (4, 113, 321, 7.25))
            self.assertAlmostEqual(p.response_h, 23 / 60)
            self.assertAlmostEqual(p.cycle_h, 47 / 60)
            self.assertAlmostEqual(p.revenue[0], (13 * 71 + 17 * 4) / 24)
