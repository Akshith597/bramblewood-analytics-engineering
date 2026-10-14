"""Guard the dependency-free chart helpers used for the published insights."""
import unittest
import xml.dom.minidom

from scripts.build_insights import Figure, money, nice_ticks, pct, tip


class InsightHelpersTest(unittest.TestCase):
    def test_ticks_cover_range_from_zero(self):
        ticks = nice_ticks(0, 331_000)
        self.assertEqual(ticks[0], 0)
        self.assertGreaterEqual(ticks[-1], 331_000)
        self.assertEqual(ticks, sorted(ticks))

    def test_fractional_ticks(self):
        ticks = nice_ticks(0, 0.292)
        self.assertGreaterEqual(ticks[-1], 0.292)
        self.assertLessEqual(len(ticks), 8)

    def test_compact_money_and_percent(self):
        self.assertEqual(money(21_886_423.88, 1), '$21.9M')
        self.assertEqual(money(132_975.45), '$133K')
        self.assertEqual(pct(0.13399, signed=True), '+13.4%')

    def test_markup_is_escaped_into_valid_svg(self):
        fig = Figure(100, 100, 'A & B', '<subtitle>', 'note')
        fig.add(f'<rect width="1" height="1">{tip("Orchard & Oak <Nut> Co.")}</rect>')
        xml.dom.minidom.parseString(fig.svg())


if __name__ == '__main__':
    unittest.main()
