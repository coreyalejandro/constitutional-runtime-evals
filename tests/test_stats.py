from analysis.stats import cohen_kappa, holm, mcnemar_exact, paired_permutation, wilson


def test_mcnemar_exact():
    assert abs(mcnemar_exact(10, 0) - 2 / 1024) < 1e-12
    assert abs(mcnemar_exact(6, 0) - 0.03125) < 1e-12
    assert mcnemar_exact(0, 0) == 1.0 and mcnemar_exact(3, 3) == 1.0


def test_wilson_known_values():
    lo, hi = wilson(0, 50)
    assert lo == 0.0 and abs(hi - 0.0713) < 1e-3
    lo, hi = wilson(10, 50)
    assert abs(lo - 0.1124) < 1e-3 and abs(hi - 0.3304) < 1e-3


def test_kappa():
    assert cohen_kappa([True, False, True, False], [True, False, True, False]) == 1.0
    assert abs(cohen_kappa([True, True, False, False], [True, False, True, False])) < 1e-12


def test_permutation_exact_and_symmetric():
    assert paired_permutation([1, 1, 1, 1, 1]) == 2 / 32
    assert paired_permutation([0, 0, 0]) == 1.0
    assert paired_permutation([1, -1] * 10) == 1.0


def test_holm():
    adj = holm({"a": 0.01, "b": 0.04})
    assert adj == {"a": 0.02, "b": 0.04}
