"""Small, dependency-free statistics used across the analyses (exact where possible)."""
from math import comb, sqrt


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion k/n."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value. b = pairs only condition 1 failed, c = only condition 2 failed."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def cohen_kappa(a: list[bool], b: list[bool]) -> float:
    """Cohen's kappa for two binary raters over the same items."""
    n = len(a)
    if n == 0 or n != len(b):
        raise ValueError("raters must label the same non-empty item list")
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def sign_test(wins: int, losses: int) -> float:
    """Two-sided exact sign test (ties dropped)."""
    return mcnemar_exact(wins, losses)


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f = 2 * p * r / (p + r) if (tp + fp and tp + fn and p + r) else float("nan")
    return {"precision": p, "recall": r, "f1": f}


def paired_permutation(diffs: list[float], n_resamples: int = 20000, seed: int = 0) -> float:
    """Two-sided paired sign-flip permutation test on per-item differences (exact if n <= 16)."""
    import itertools, random
    d = [x for x in diffs]
    n = len(d)
    if n == 0:
        return float("nan")
    obs = abs(sum(d))
    if n <= 16:
        hits = sum(abs(sum(s * x for s, x in zip(signs, d))) >= obs - 1e-12 for signs in itertools.product((1, -1), repeat=n))
        return hits / 2 ** n
    rng = random.Random(seed)
    hits = sum(abs(sum(x if rng.random() < 0.5 else -x for x in d)) >= obs - 1e-12 for _ in range(n_resamples))
    return (hits + 1) / (n_resamples + 1)


def bootstrap_mean_ci(values: list[float], n_resamples: int = 10000, seed: int = 0) -> tuple[float, float]:
    """Percentile 95% CI for the mean of per-item values (items = prompts, so samples are clustered)."""
    import random
    if not values:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(values)
    ms = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_resamples))
    return (ms[int(0.025 * n_resamples)], ms[int(0.975 * n_resamples) - 1])


def holm(pvals: dict) -> dict:
    """Holm-Bonferroni adjusted p-values."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out
