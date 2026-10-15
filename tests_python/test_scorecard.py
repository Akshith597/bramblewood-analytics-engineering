"""The scorecard scores frozen estimates, so any change to a scored estimate after the freeze must fail CI."""
import json
import unittest

from analysis.scorecard import FROZEN, collect, score_rows


class ScorecardTest(unittest.TestCase):
    def test_results_still_match_frozen_estimates(self):
        frozen = {p['id']: p for p in json.loads(FROZEN.read_text(encoding='utf-8'))['parameters']}
        current = {p['id']: p for p in collect()}
        self.assertEqual(sorted(frozen), sorted(current), 'Scored parameter set changed after the freeze')
        drift = [k for k in frozen if (frozen[k]['estimate'], frozen[k]['ci90']) != (current[k]['estimate'],
                                                                                    current[k]['ci90'])]
        self.assertFalse(drift, f'Estimates changed after the freeze (log in DEVIATIONS.md, do not re-tune): {drift}')

    def test_every_parameter_has_an_interval(self):
        missing = [p['id'] for p in json.loads(FROZEN.read_text(encoding='utf-8'))['parameters'] if not p['ci90']]
        self.assertFalse(missing, f'Frozen without a 90% interval: {missing}')

    def test_coverage_rule(self):
        frozen = [{'id': 'a', 'family': 'delist', 'parameter': 'a', 'estimate': 1.0, 'ci90': [0.5, 1.5]},
                  {'id': 'b', 'family': 'delist', 'parameter': 'b', 'estimate': 1.0, 'ci90': [0.5, 1.5]},
                  {'id': 'c', 'family': 'delist', 'parameter': 'c', 'estimate': 1.0, 'ci90': [0.5, 1.5]}]
        r = score_rows(frozen, {'a': 0.5, 'b': 1.6, 'z': 0.0})
        self.assertEqual((r['scored'], r['covered']), (2, 1))       # interval ends are inclusive
        self.assertEqual([w['id'] for w in r['proved_wrong']], ['b'])
        self.assertAlmostEqual(r['rows'][1]['error'], -0.6)
        self.assertEqual(r['unmapped_key_ids'], ['z'])
        self.assertIsNone(r['rows'][2]['truth'])


if __name__ == '__main__':
    unittest.main()
