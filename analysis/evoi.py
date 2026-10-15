"""Rank the proposed randomized tests by expected value of sample information (EVSI) against their cost.

Each test informs one plan decision. The prior for the uncertain quantity is the plan model's (analysis/plan.py).
A test returns an estimate y = θ + noise with a stated standard error; the decision is then taken on the
posterior mean (normal–normal update). EVSI = E[payoff of the decision taken after the test] − payoff of the
best decision today, over a decision horizon of two years (FY2026–FY2027, undiscounted). Cost = GP forgone by
running the non-preferred arm in the test stores for the test's length (expected, under today's prior) + a fixed
execution cost (an assumption; the same for every test so it does not drive the ranking).
EVPI (perfect information) is shown alongside as the ceiling.

Tests (from the memo and the plan):
1. Tortilla price — private-label tortilla price held in a random half of stores and rolled back in the other half
   for 13 weeks. Decision: keep or roll back. θ = own-price elasticity. Test SE: the pre-registered tortilla event
   design's store-clustered SE (a 13-week, all-store comparison), as the best data-based proxy.
2. Assortment — the cut list in a random half of matched large-store pairs for a full year. Decision: cut chain-
   wide or not. θ = transfer rate τ. Test SE: today's SE scaled by √(26/52) for twice the post-period.
3. Display holdout — display events withheld from a random quarter of stores for half a year. Decision: keep
   display events or drop them. θ = display events' GP before funding (model error) — the vendor funding share ρ
   that also drives this decision is a negotiation, not something a test measures; its EVPI is shown separately.
"""
import json
import math
import random

from analysis.common import RESULTS, connect, round_floats, write_result
from analysis.plan import KEEP_CELLS, build_inputs, gp_change, res

SEED = 20261016
DRAWS = 20000
HORIZON_YEARS = 2.0
EXECUTION_COST = 5000.0


def posterior_mean(prior_mean, prior_sd, y, se):
    w = prior_sd ** 2 / (prior_sd ** 2 + se ** 2)
    return prior_mean + w * (y - prior_mean)


def value(draws, payoff, actions, se, signal):
    """EVSI and EVPI for a decision with payoff(action, θ); draws are θ; signal(θ, rng) gives y."""
    rng = random.Random(SEED)
    prior_value = {a: sum(payoff(a, t) for t in draws) / len(draws) for a in actions}
    best_now = max(prior_value, key=prior_value.get)
    evpi = sum(max(payoff(a, t) for a in actions) for t in draws) / len(draws) - prior_value[best_now]
    m = sum(draws) / len(draws)
    sd = math.sqrt(sum((t - m) ** 2 for t in draws) / (len(draws) - 1))
    total = 0.0
    for t in draws:
        post = posterior_mean(m, sd, signal(t, rng), se)
        total += payoff(max(actions, key=lambda a: payoff(a, post)), t)   # payoffs are linear or monotone in θ
    return {'best_action_today': best_now, 'prior_value': prior_value,
            # EVSI cannot be negative; values within Monte Carlo noise of zero are reported as zero.
            'evsi': max(total / len(draws) - prior_value[best_now], 0.0), 'evpi': evpi, 'prior_mean': m, 'prior_sd': sd,
            'test_se': se}


def main():
    con = connect()
    inp = build_inputs(con)
    pricing, delist = res('pricing'), res('delist')
    rng = random.Random(SEED)
    out = {}

    # 1. Tortilla price: payoff per year of keeping vs rolling back = G(ε) vs 0.
    p = inp['price']['bramble_select_tortilla']
    se = pricing['preregistered']['bramble_select_tortilla']['x_own']['se_store_cr1']
    eps = [rng.gauss(p['eps'], p['eps_sd']) for _ in range(DRAWS)]
    pay = lambda a, e: HORIZON_YEARS * (gp_change(p, e) if a == 'keep' else 0.0)
    r = value(eps, pay, ('keep', 'roll_back'), se, lambda t, g: t + g.gauss(0, se))
    loser_share = 0.5 * 13 / 52
    r['opportunity_cost'] = loser_share * abs(r['prior_value']['keep'] - r['prior_value']['roll_back']) / HORIZON_YEARS
    out['tortilla_price'] = r

    # 2. Assortment: payoff of cutting = A + τB per year, of not cutting = 0.
    a = inp['assortment']
    taus = [rng.gauss(a['tau'], a['tau_sd']) for _ in range(DRAWS)]
    se = a['tau_sd'] * math.sqrt(26 / 52)
    pay = lambda act, t: HORIZON_YEARS * ((a['a'] + t * a['b']) if act == 'cut' else 0.0)
    r = value(taus, pay, ('cut', 'keep_all'), se, lambda t, g: t + g.gauss(0, se))
    # Holding the cut back in half the large stores for a year forgoes that share of the large-format gain.
    large = res('assortment')['by_planogram']['PG-SS-L-2024']
    r['opportunity_cost'] = 0.5 * max(large['chain_a'] + a['tau'] * large['chain_b'], 0.0)
    out['assortment_cut'] = r

    # 3. Display events: payoff per year of dropping = −GPbf − (1 − ρ)·funding; keeping = 0. θ = GPbf error.
    promo = inp['promo']
    gpbf = sum(promo[c]['gp_before_funding'] * (1 - promo[c]['cut_sku_event_share']) for c in KEEP_CELLS)
    sd = sum(promo[c]['sd'] for c in KEEP_CELLS)
    funding = sum((promo[c]['scan_back'] + promo[c]['display_fee']) * (1 - promo[c]['cut_sku_event_share'])
                  for c in KEEP_CELLS)
    rho_mean = 0.5
    errs = [rng.gauss(0, sd) for _ in range(DRAWS)]
    pay = lambda act, e: HORIZON_YEARS * ((-(gpbf + e) - (1 - rho_mean) * funding) if act == 'drop' else 0.0)
    holdout_se = sd * math.sqrt(4 * 2)      # a quarter of stores for half a year vs today's full-year all-store fit
    r = value(errs, pay, ('keep', 'drop'), holdout_se, lambda t, g: t + g.gauss(0, holdout_se))
    r['opportunity_cost'] = 0.25 * 0.5 * abs(r['prior_value']['drop'] - r['prior_value']['keep']) / HORIZON_YEARS
    # EVPI of the funding share itself (not testable; settled by negotiation).
    rhos = [rng.betavariate(2, 2) for _ in range(DRAWS)]
    pay_rho = lambda act, rho: HORIZON_YEARS * ((-gpbf - (1 - rho) * funding) if act == 'drop' else 0.0)
    r['funding_share_evpi'] = value(rhos, pay_rho, ('keep', 'drop'), 1e9, lambda t, g: t)['evpi']
    r['note'] = ('Decision evaluated at the prior-mean funding share; the funding share, not the GP model, decides '
                 'this lever, and it is settled at the negotiating table.')
    out['display_holdout'] = r

    for k, r in out.items():
        r['execution_cost'] = EXECUTION_COST
        r['total_cost'] = r['opportunity_cost'] + EXECUTION_COST
        r['net_value'] = r['evsi'] - r['total_cost']
    ranking = sorted(out, key=lambda k: -out[k]['net_value'])
    result = {'design': {'draws': DRAWS, 'seed': SEED, 'horizon_years': HORIZON_YEARS,
                         'execution_cost_assumed': EXECUTION_COST},
              'tests': out, 'ranking': ranking}
    write_result('evoi', round_floats(result))
    return result


if __name__ == '__main__':
    r = round_floats(main())
    for k in r['ranking']:
        t = r['tests'][k]
        print(k, {x: t[x] for x in ('best_action_today', 'evsi', 'evpi', 'opportunity_cost', 'total_cost', 'net_value',
                                    'prior_mean', 'prior_sd', 'test_se')}, t.get('funding_share_evpi'))
