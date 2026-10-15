"""Guard the decision memo against drift from its query results and against hand-typed figures."""
import re
import unittest

from analysis.build_memo import MEMO, TEMPLATE, render

# Numbers allowed as literal text: design constants fixed in analysis/PLAN.md, not results.
DESIGN_CONSTANTS = {'2024', '2025', '2026', 'FY2024', 'FY2025', 'FY2026', 'W27', '102', '106', '113', '116',
                    '1', '2', '3', '4', '5', '13', '80%', '90%', '2%', '1.5',
                    '6', '7', '8', '9', '10'}  # last line: deviation-list enumerators


class MemoTest(unittest.TestCase):
    def test_committed_memo_matches_results(self):
        self.assertEqual(MEMO.read_text(encoding='utf-8'), render(),
                         'docs/decision_memo.md is stale: run python -m analysis.build_memo')

    def test_template_has_no_hand_typed_results(self):
        text = re.sub(r'\{\w+\}', '', TEMPLATE.read_text(encoding='utf-8'))
        text = re.sub(r'\]\([^)]*\)', ']', text)          # link targets
        tokens = set(re.findall(r'(?:FY)?\d[\d.,]*%?|W\d+', text))
        tokens = {t.rstrip('.,') for t in tokens}
        unexpected = tokens - DESIGN_CONSTANTS
        self.assertFalse(unexpected, f'Numbers typed into the memo template instead of results: {sorted(unexpected)}')


if __name__ == '__main__':
    unittest.main()
