import json, subprocess, sys


def test_april_reanalysis_numbers():
    subprocess.run([sys.executable, "-m", "analysis.reanalyze_april"], check=True, capture_output=True)
    o = json.load(open("results/april_reanalysis.json"))
    p = o["primary_run_50"]
    assert (p["baseline_violations"], p["constitution_violations"], p["n_cases"]) == (10, 0, 50)
    assert p["mcnemar_exact_p"] == round(2 / 1024, 4)
    assert o["secondary_run_25"]["baseline_violations"] == 6
    assert sum(o["silent_judge_fallbacks_per_run"].values()) == 0
    assert len(o["run_history"]) == 9
    assert o["bid_vs_cot_april"]["distinct_score_pairs"] == [["2", "1"]]
