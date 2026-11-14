"""Run every decision analysis in dependency order, then render the memo. Requires a built warehouse."""

import importlib
import time

STEPS = [
    'business_analysis.delist',
    'business_analysis.pricing',
    'business_analysis.forecast',
    'business_analysis.funding',
    'business_analysis.promotions',
    'business_analysis.stockouts',
    'business_analysis.physical',
    'business_analysis.assortment',
    'business_analysis.inventory_sim',
    'business_analysis.plan',
    'business_analysis.crosscheck',
    'business_analysis.scorecard',
    'business_analysis.build_memo',
    'business_analysis.build_plan',
    'business_analysis.build_public',
]


def main():
    for step in STEPS:
        started = time.time()
        importlib.import_module(step).main()
        print(f'{step}: {time.time() - started:.0f}s')


if __name__ == '__main__':
    main()
