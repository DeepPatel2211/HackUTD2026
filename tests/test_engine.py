import json
import unittest
from fastapi.testclient import TestClient
from backend.engine import Dataset, ROOT, simulate
from backend.main import app


class SimulatorTests(unittest.TestCase):
    def test_trip_between_events_accounts_for_lost_revenue(self):
        r = simulate(100, 92, 50, 6, [240], [100], [], 6, [], 150, 905)
        self.assertTrue(r['tripped'])
        self.assertAlmostEqual(r['cost'], 180)

    def test_late_truck_does_not_reverse_a_trip(self):
        r = simulate(100, 92, 80, 6, [240], [100], [], 6, [2], 20, 50)
        self.assertTrue(r['tripped'])
        self.assertAlmostEqual(r['cost'], 530)

    def test_truck_cannot_take_more_than_tank_contains(self):
        self.assertIsNone(simulate(100, 92, 10, 6, [24], [100], [], 6, [1], 50, 50))

    def test_timed_shut_in_cost_and_water(self):
        r = simulate(100, 92, 50, 6, [240], [100], [0], 4, [], 150, 905)
        self.assertFalse(r['tripped'])
        self.assertEqual(r['cost'], 200)
        self.assertAlmostEqual(r['trace'][-1]['level_pct'],90)


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = Dataset('history/full_week')

    def test_event_9_calculates_one_truck(self):
        # Answer keys are validation fixtures only. Runtime engine never opens them.
        event = next(e for e in json.loads((ROOT/'history/full_week/answer_key.json').read_text()) if e['id']=='EVENT_9')
        r = self.data.analyze(event['onset_unix'])
        alert = next(a for a in r['alerts'] if a['facility_id']==event['facility'])
        plan = alert['recommendation']
        self.assertEqual(plan['cost'],905)
        self.assertEqual(plan['trucks'],1)
        self.assertFalse(plan['tripped'])

    def test_shared_fleet_at_each_pump_event(self):
        events=json.loads((ROOT/'history/full_week/answer_key.json').read_text())
        for event in events:
            if event['category']!='pump_failure':
                continue
            r=self.data.analyze(event['onset_unix'])
            for sid,ops in self.data.ops['systems'].items():
                used=sum(a['recommendation'].get('trucks',0) for a in r['alerts'] if a['system_id']==sid)
                self.assertLessEqual(used,ops['emergency_fleet_size'])

    def test_normal_pump_cycle_is_not_failure(self):
        r=self.data.analyze(self.data.start)
        self.assertEqual(r['alerts'],[])

    def test_path_traversal_rejected(self):
        with self.assertRaises(ValueError):
            Dataset('../../outside')

    def test_api_and_missing_ai_credentials(self):
        client=TestClient(app)
        self.assertEqual(client.get('/api/health').status_code,200)
        self.assertGreater(len(client.get('/api/datasets').json()),0)
        self.assertEqual(client.get('/api/dashboard',params={'dataset':'../../outside'}).status_code,400)


if __name__=='__main__':
    unittest.main()
