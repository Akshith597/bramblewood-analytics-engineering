"""Fixed-effects OLS on DuckDB, with cluster-robust and wild-bootstrap inference.

Absorbed fixed effects are removed by alternating projections (method of alternating projections /
Guimarães–Portugal), executed as DuckDB window queries so panels never leave the database. The small
k×k algebra is done in plain Python. Small-sample convention: CR1 with c = G/(G-1), matching
`fixest::feols(..., ssc = ssc(adj = FALSE, cluster.adj = TRUE))`.
"""
import math
import random

WEBB = (-math.sqrt(1.5), -1.0, -math.sqrt(0.5), math.sqrt(0.5), 1.0, math.sqrt(1.5))


def invert(matrix):
    """Gauss–Jordan inverse of a small dense matrix."""
    n = len(matrix)
    aug = [list(map(float, row)) + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-14:
            raise ValueError('Singular design matrix: a regressor is collinear with the fixed effects')
        aug[col], aug[pivot] = aug[pivot], aug[col]
        p = aug[col][col]
        aug[col] = [v / p for v in aug[col]]
        for r in range(n):
            if r != col and aug[r][col]:
                f = aug[r][col]
                aug[r] = [a - f * b for a, b in zip(aug[r], aug[col])]
    return [row[n:] for row in aug]


def matvec(m, v):
    return [sum(a * b for a, b in zip(row, v)) for row in m]


def quantile(values, q):
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def demean(con, source, columns, fes, tol=1e-10, max_iter=1000):
    """Create temp table `_dm` holding `columns` with every FE in `fes` projected out."""
    keep = ', '.join(sorted(set(fes)))
    con.execute(f'create or replace temp table _dm as select {keep}, cluster_id, {", ".join(columns)} from {source}')
    for iteration in range(max_iter):
        for fe in fes:
            replaced = ', '.join(f'{c} - avg({c}) over (partition by {fe}) as {c}' for c in columns)
            con.execute(f'create or replace temp table _dm as select * replace ({replaced}) from _dm')
        if len(fes) == 1:
            return iteration + 1
        # After a sweep only the earlier FEs can have drifted; converged when every group mean is ~0.
        drift = con.execute(' union all '.join(
            f'select max(abs(m)) from (select avg({c}) as m from _dm group by {fe})'
            for fe in fes[:-1] for c in columns)).fetchall()
        drift = max(row[0] for row in drift)
        if drift < tol:
            return iteration + 1
    raise RuntimeError(f'Fixed effects did not converge within {max_iter} iterations (drift {drift})')


def feols(con, source, y, xs, fes, cluster_label='cluster'):
    """OLS of y on xs with absorbed `fes`; `source` must expose a `cluster_id` column."""
    iterations = demean(con, source, [y, *xs], fes)
    k = len(xs)
    sums = con.execute('select count(*), ' + ', '.join(
        [f'sum({a} * {b})' for a in xs for b in xs] + [f'sum({a} * {y})' for a in xs]) + ' from _dm').fetchone()
    n = sums[0]
    xtx = [list(sums[1 + i * k:1 + (i + 1) * k]) for i in range(k)]
    xty = list(sums[1 + k * k:])
    bread = invert(xtx)
    beta = matvec(bread, xty)
    residual = f'({y} - ' + ' - '.join(f'{b!r} * {x}' for b, x in zip(beta, xs)) + ')'
    scores = con.execute('select cluster_id, ' + ', '.join(f'sum({x} * {residual})' for x in xs)
                         + ' from _dm group by cluster_id order by cluster_id').fetchall()
    g = len(scores)
    meat = [[sum(s[1 + i] * s[1 + j] for s in scores) for j in range(k)] for i in range(k)]
    c = g / (g - 1)
    vcov = [[c * v for v in row] for row in
            [[sum(bread[i][a] * meat[a][b] * bread[b][j] for a in range(k) for b in range(k))
              for j in range(k)] for i in range(k)]]
    return {'beta': dict(zip(xs, beta)), 'se': dict(zip(xs, (math.sqrt(vcov[i][i]) for i in range(k)))),
            'n': n, 'clusters': g, 'cluster': cluster_label, 'fe_iterations': iterations,
            '_vcov': vcov, '_bread': bread, '_scores': [list(s[1:]) for s in scores]}


def wild_draws(fit, draws=9999, seed=20261014):
    """Unrestricted wild cluster bootstrap (Webb weights) coefficient vectors.

    beta* - beta = (X'X)^-1 sum_g w_g s_g, where s_g are the cluster score vectors, so no refitting is needed.
    """
    names = list(fit['beta'])
    base = [fit['beta'][x] for x in names]
    rng = random.Random(seed)
    out = []
    for _ in range(draws):
        shock = [0.0] * len(names)
        for score in fit['_scores']:
            w = rng.choice(WEBB)
            for i, v in enumerate(score):
                shock[i] += w * v
        out.append(dict(zip(names, (b + d for b, d in zip(base, matvec(fit['_bread'], shock))))))
    return out


def wald_pvalue(fit, names):
    """Joint test that `names` are all zero using the CR1 covariance; chi-square reference."""
    idx = [list(fit['beta']).index(x) for x in names]
    sub = [[fit['_vcov'][i][j] for j in idx] for i in idx]
    b = [fit['beta'][x] for x in names]
    stat = sum(bi * v for bi, v in zip(b, matvec(invert(sub), b)))
    return stat, chi2_sf(stat, len(names))


def chi2_sf(x, k):
    """Survival function of the chi-square distribution via the regularized lower incomplete gamma."""
    a, z = k / 2, x / 2
    if z <= 0:
        return 1.0
    if z < a + 1:  # series expansion
        term = total = 1 / a
        n = 1
        while abs(term) > 1e-15 * abs(total):
            term *= z / (a + n)
            total += term
            n += 1
        lower = total * math.exp(-z + a * math.log(z) - math.lgamma(a))
        return max(0.0, 1 - lower)
    # continued fraction (Lentz) for the upper tail
    tiny = 1e-300
    b, c, d = z + 1 - a, 1 / tiny, 1 / (z + 1 - a)
    h = d
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
    return math.exp(-z + a * math.log(z) - math.lgamma(a)) * h


def wild_percentile_ci(fit, x, level=0.90, draws=9999, seed=20261014, samples=None):
    """Symmetric percentile CI for one coefficient from unrestricted wild cluster bootstrap draws."""
    samples = samples or wild_draws(fit, draws, seed)
    b = fit['beta'][x]
    half = quantile([abs(s[x] - b) for s in samples], level)
    return [b - half, b + half]


def clustered_ci(fit, x, level=0.90):
    z = {0.90: 1.6448536269514722, 0.95: 1.959963984540054}[level]
    return [fit['beta'][x] - z * fit['se'][x], fit['beta'][x] + z * fit['se'][x]]
