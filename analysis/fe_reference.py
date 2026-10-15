"""Independent pure-Python fixed-effects OLS used to cross-check analysis/fe.py.

Shares no code with fe.py: rows are pulled into Python, FEs are swept with dictionaries, and the normal
equations are solved by Cramer's rule / explicit 2x2 algebra (k <= 2) or a Cholesky factorisation (k > 2, not
the Gauss-Jordan inverse fe.py uses), so a bug in one path cannot hide in both.
"""
import math
from collections import defaultdict


def _sweep(rows, columns, fe):
    totals, counts = defaultdict(lambda: [0.0] * len(columns)), defaultdict(int)
    for r in rows:
        key = r[fe]
        counts[key] += 1
        acc = totals[key]
        for i, c in enumerate(columns):
            acc[i] += r[c]
    for r in rows:
        acc, n = totals[r[fe]], counts[r[fe]]
        for i, c in enumerate(columns):
            r[c] -= acc[i] / n


def _cholesky_inverse(a):
    """Inverse of a symmetric positive-definite matrix via A = L L'."""
    n = len(a)
    low = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            acc = a[i][j] - sum(low[i][k] * low[j][k] for k in range(j))
            low[i][j] = math.sqrt(acc) if i == j else acc / low[j][j]
    inv_low = [[0.0] * n for _ in range(n)]
    for i in range(n):
        inv_low[i][i] = 1 / low[i][i]
        for j in range(i):
            inv_low[i][j] = -sum(low[i][k] * inv_low[k][j] for k in range(j, i)) / low[i][i]
    return [[sum(inv_low[k][i] * inv_low[k][j] for k in range(max(i, j), n)) for j in range(n)] for i in range(n)]


def feols_reference(rows, y, xs, fes, tol=1e-10, max_iter=5000):
    rows = [dict(r) for r in rows]
    columns = [y, *xs]
    for _ in range(max_iter):
        for fe in fes:
            _sweep(rows, columns, fe)
        if len(fes) == 1:
            break
        worst = 0.0
        for fe in fes[:-1]:
            sums, counts = defaultdict(float), defaultdict(int)
            for r in rows:
                for c in columns:
                    sums[(r[fe], c)] += r[c]
                counts[r[fe]] += 1
            worst = max(worst, max(abs(v) / counts[key[0]] for key, v in sums.items()))
        if worst < tol:
            break
    if len(xs) == 1:
        (x,) = xs
        sxx = sum(r[x] ** 2 for r in rows)
        beta = [sum(r[x] * r[y] for r in rows) / sxx]
        bread = [[1 / sxx]]
    elif len(xs) == 2:
        a, b = xs
        saa = sum(r[a] ** 2 for r in rows)
        sbb = sum(r[b] ** 2 for r in rows)
        sab = sum(r[a] * r[b] for r in rows)
        say = sum(r[a] * r[y] for r in rows)
        sby = sum(r[b] * r[y] for r in rows)
        det = saa * sbb - sab ** 2
        beta = [(sbb * say - sab * sby) / det, (saa * sby - sab * say) / det]
        bread = [[sbb / det, -sab / det], [-sab / det, saa / det]]
    else:
        xtx = [[sum(r[a] * r[b] for r in rows) for b in xs] for a in xs]
        xty = [sum(r[a] * r[y] for r in rows) for a in xs]
        bread = _cholesky_inverse(xtx)
        beta = [sum(bread[i][j] * xty[j] for j in range(len(xs))) for i in range(len(xs))]
    k = len(xs)
    scores = defaultdict(lambda: [0.0] * k)
    for r in rows:
        e = r[y] - sum(bv * r[x] for bv, x in zip(beta, xs))
        for i, x in enumerate(xs):
            scores[r['cluster_id']][i] += r[x] * e
    g = len(scores)
    se = []
    for i in range(k):
        var = sum((sum(bread[i][a] * s[a] for a in range(k))) ** 2 for s in scores.values())
        se.append(math.sqrt(var * g / (g - 1)))
    return {'beta': dict(zip(xs, beta)), 'se': dict(zip(xs, se)), 'n': len(rows), 'clusters': g}
