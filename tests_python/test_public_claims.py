"""Guard every public claim (README, FY2026 plan, scorecard) against drift from results and hand-typed figures."""
import re
import unittest

from analysis import build_plan, build_public

# Numbers allowed as literal text outside placeholders: tool versions in badges and commands, design constants
# fixed in analysis/PLAN.md or the plan model, and list enumerators.
ALLOWED = {'2024', '2025', '2026', 'FY2024', 'FY2025', 'FY2026', 'W27', '1', '2', '3', '4', '5', '13', '20', '90%',
           '1.12', '1.5', '3.12', '8080', '25%'}


def hand_typed(text):
    text = re.sub(r'```.*?```', '', text, flags=re.S)                  # code blocks (commands, mermaid)
    text = re.sub(r'^\s*!?\[!?\[?.*$', '', text, flags=re.M)            # badge and image lines
    text = re.sub(r'\{\{|\}\}', '', text)
    text = re.sub(r'\{\w+\}', '', text)
    text = re.sub(r'\]\([^)]*\)', ']', text)                          # link targets
    text = re.sub(r'`[^`]*`', '', text)                               # inline code (tag names, paths)
    # Not inside words such as GitHub handles ("Akshith597").
    tokens = {t.rstrip('.,') for t in re.findall(r'(?<![\w.])(?:FY)?\d[\d.,]*%?|W\d+', text)}
    return sorted(tokens - ALLOWED)


class PublicClaimsTest(unittest.TestCase):
    def test_readme_matches_results(self):
        self.assertEqual(build_public.README.read_text(encoding='utf-8'), build_public.render(),
                         'README.md is stale: run python -m analysis.build_public')

    def test_plan_and_scorecard_match_results(self):
        self.assertEqual(build_plan.PLAN.read_text(encoding='utf-8'), build_plan.render_plan(),
                         'docs/fy2026_plan.md is stale: run python -m analysis.build_plan')
        self.assertEqual(build_plan.SCORECARD.read_text(encoding='utf-8'), build_plan.render_scorecard(),
                         'docs/scorecard.md is stale: run python -m analysis.build_plan')

    def test_templates_have_no_hand_typed_results(self):
        for template in (build_public.TEMPLATE, build_plan.PLAN_TEMPLATE, build_plan.SCORE_TEMPLATE):
            with self.subTest(template=template.name):
                self.assertFalse(hand_typed(template.read_text(encoding='utf-8')),
                                 f'Numbers typed into {template.name} instead of results')


if __name__ == '__main__':
    unittest.main()
