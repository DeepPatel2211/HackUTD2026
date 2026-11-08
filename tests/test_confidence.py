import unittest
from types import SimpleNamespace

from backend.dataset import Series
from backend.detect import evidence_confidence


class ConfidenceTests(unittest.TestCase):
    def evidence(self, flow, pressure, now=0, state=2):
        channels = {
            ('P', 'status'): Series([(0, state), (300, 2)]),
            ('P', 'flow_bpd'): Series([(0, flow), (300, 0)]),
            ('P', 'discharge_psi'): Series([(0, pressure), (300, 1000)]),
        }
        data = SimpleNamespace(system_of={'F': {'disposal_site': {'pressure_psi': 1000}}},
                               channel=lambda asset, metric: channels.get((asset, metric), Series([])))
        facility = {'id': 'F', 'pump': {'id': 'P', 'max_flow_bpd': 100}, 'pipeline': {'id': 'L'}}
        base = SimpleNamespace(flow_scale=1, disch_offset=100)
        return evidence_confidence(data, facility, 'pump_failure', 0, now, base)

    def test_full_corroboration_can_reach_100_but_is_not_fixed(self):
        strong = self.evidence(0, 1000)
        weak = self.evidence(100, 1100)
        self.assertEqual(strong['confidence'], 1)
        self.assertAlmostEqual(weak['confidence'], 1 / 3, places=6)
        self.assertFalse(strong['confidence_basis']['calibrated_probability'])

    def test_future_readings_do_not_inflate_earlier_replay_confidence(self):
        early = self.evidence(100, 1100, now=0)
        later = self.evidence(100, 1100, now=300)
        self.assertLess(early['confidence'], later['confidence'])
        self.assertEqual(early['confidence_basis']['samples'], 1)
        self.assertEqual(later['confidence_basis']['samples'], 2)

    def test_partial_corroboration_is_measured_continuously(self):
        self.assertAlmostEqual(self.evidence(50, 1050)['confidence'], 2 / 3, places=6)

    def test_no_samples_returns_zero_not_a_default_high_score(self):
        self.assertEqual(self.evidence(0, 1000, now=-1)['confidence'], 0)
