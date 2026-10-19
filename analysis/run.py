"""Run every decision analysis in dependency order, then render the memo. Requires a built warehouse."""
import importlib
import time

STEPS = ['analysis.delist', 'analysis.pricing', 'analysis.forecast', 'analysis.funding', 'analysis.promotions',
         'analysis.stockouts', 'analysis.physical', 'analysis.assortment', 'analysis.inventory_sim', 'analysis.plan',
         'analysis.evoi', 'analysis.crosscheck', 'analysis.scorecard', 'analysis.build_memo', 'analysis.build_plan',
         'analysis.build_public']


def main():
    for step in STEPS:
        started = time.time()
        importlib.import_module(step).main()
        print(f'{step}: {time.time() - started:.0f}s')


if __name__ == '__main__':
    main()
