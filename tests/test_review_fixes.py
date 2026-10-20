"""Regression tests for the independent review of v0.1.0 (reviews/INDEPENDENT_REVIEW_v0.1.0.md).
Each test names the finding it covers. No network, no API key, no cost."""
import json, os, threading

import pytest

from analysis import analyze_constitutional
from analysis.analyze_constitutional import response_verdicts
from analysis.stats import holm, sign_test
from evals import april_prompts as AP
from evals import common, run_constitutional
from evals.common import Budget, BudgetExceeded, Store, load_jsonl, price, resolve_models, sanitize
from evals.providers import Completion
from evals.run_bid_cot import validate
from evals.run_constitutional import generic_safety_prompt, parse_judgment


def args_for(tmp_path, name, *extra):
    return ["--name", name, "--outroot", str(tmp_path), "--ledger", str(tmp_path / "SPEND.jsonl"), *extra]


# A1: concurrent workers cannot overshoot the cap; unknown outcomes are charged in full
def test_A1_budget_reserves_atomically(tmp_path):
    b = Budget(0.01, str(tmp_path / "s.jsonl"))
    ok, refused = [], []

    def worker():
        try:
            ok.append(b.reserve("claude-sonnet-4-6", 0, 200, "t"))  # $0.003 each
        except BudgetExceeded:
            refused.append(1)

    ts = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len(ok) == 3 and len(refused) == 5  # 3 x $0.003 <= $0.01 < 4 x $0.003
    rid, usd = ok[0]
    b.settle(rid, usd, "claude-sonnet-4-6", None, "t")  # outcome unknown
    assert abs(b.spent() - usd) < 1e-9


def test_A1_settles_at_actual_usage(tmp_path):
    b = Budget(1.0, str(tmp_path / "s.jsonl"))
    rid, usd = b.reserve("claude-haiku-4-5", 1000, 500, "t")
    b.settle(rid, usd, "claude-haiku-4-5", Completion("x", "end_turn", 100, 10), "t")
    assert abs(b.spent() - (100 * 1 + 10 * 5) / 1e6) < 1e-12


# A2: a resume with different settings is refused; judgments are bound to the response text
def test_A2_incompatible_resume_refused(tmp_path):
    base = ["--targets", "fake-target", "--judges", "fake-judge", "--limit", "1", "--splits", "heldout"]
    run_constitutional.main(args_for(tmp_path, "r", *base, "--samples", "2"))
    with pytest.raises(SystemExit):
        run_constitutional.main(args_for(tmp_path, "r", *base, "--samples", "1"))
    with pytest.raises(SystemExit):
        run_constitutional.main(args_for(tmp_path, "r", *base, "--samples", "2", "--temperature", "0.25"))


def test_A2_analysis_ignores_rows_outside_config_and_unbound_judgments(tmp_path):
    run_constitutional.main(args_for(tmp_path, "r", "--targets", "fake-target", "--judges", "fake-judge", "--limit", "1",
                                     "--splits", "heldout", "--samples", "1"))
    d = tmp_path / "r"
    rows = load_jsonl(d / "responses.jsonl")
    extra = dict(rows[0], key=rows[0]["key"].replace("|0", "|9"), sample=9)
    with open(d / "responses.jsonl", "a") as f:
        f.write(json.dumps(extra) + "\n")
    js = load_jsonl(d / "judgments.jsonl")
    js[0]["response_sha256"] = "0" * 64  # judgment of different text
    with open(d / "judgments.jsonl", "w") as f:
        for j in js:
            f.write(json.dumps(j) + "\n")
    out = tmp_path / "o"
    analyze_constitutional.main(["--run", str(d), "--out", str(out)])
    c = json.load(open(out / "analysis.json"))["counts"]
    assert c["rows_outside_this_run_ignored"] == 1 and c["judgments_unbound_ignored"] == 1


# A3: one missing-data rule; parse failures retried; incomplete runs exit non-zero
def test_A3_known_violation_survives_missing_principle():
    resp = [{"key": "k"}]
    js = [{"judge": "j", "response_key": "k", "principle": "P1", "status": "ok", "violation": True}]
    assert response_verdicts(resp, js, "j")[0]["k"] is True
    js = [{"judge": "j", "response_key": "k", "principle": f"P{i}", "status": "ok", "violation": False} for i in range(3)]
    assert response_verdicts(resp, js, "j")[0]["k"] is None  # 3 of 4 clean is missing, never safe
    js.append({"judge": "j", "response_key": "k", "principle": "P3", "status": "ok", "violation": False})
    assert response_verdicts(resp, js, "j")[0]["k"] is False


def test_A3_invalid_outputs_are_retried(tmp_path):
    s = Store(str(tmp_path / "x.jsonl"))
    s.add({"key": "a", "status": "invalid"})
    assert not s.done("a")
    s.add({"key": "a", "status": "invalid"}); s.add({"key": "a", "status": "invalid"})
    assert s.done("a") and s.attempts("a") == common.MAX_ATTEMPTS  # final-missing after bounded retries


def test_A3_failed_run_is_incomplete(tmp_path, monkeypatch):
    from evals import providers
    monkeypatch.setattr(providers.FakeProvider, "complete",
                        lambda self, *a, **k: Completion("", None, 0, 0, "Timeout: simulated", 1))
    with pytest.raises(SystemExit) as e:
        run_constitutional.main(args_for(tmp_path, "f", "--targets", "fake-target", "--judges", "fake-judge", "--limit", "1",
                                         "--splits", "heldout", "--samples", "1", "--no-probes"))
    assert e.value.code == 3
    comp = json.load(open(tmp_path / "f" / "completion.json"))
    assert comp["complete"] is False and comp["responses"] == [0, 3]
    assert len(load_jsonl(tmp_path / "f" / "responses.jsonl")) == 3 * common.MAX_ATTEMPTS  # bounded retries


# A4: the pairwise unit is the question; the pairwise test is in the Holm family
def test_A4_one_question_is_one_unit():
    assert sign_test(1, 0) == 1.0  # one BID-winning question, not two samples


# A5: the control matches the constitution prompt except for the four rules
def test_A5_control_matches_constitution_framing():
    g, c = generic_safety_prompt("q")[0], AP.constitution_prompt("q")[0]
    gl, cl = g.splitlines(), c.splitlines()
    assert gl[0] == cl[0] and gl[-1] == cl[-1] and len(gl) == len(cl)
    assert sum(l.startswith("- ") for l in gl) == sum(l.startswith("- ") for l in cl) == 4


# A6: model list failure fails closed; aliases resolve to the single dated snapshot
class _P:
    def __init__(self, listed): self.listed = listed
    def list_models(self): return self.listed


def test_A6_model_resolution():
    with pytest.raises(SystemExit):
        resolve_models(["claude-haiku-4-5"], {"claude-haiku-4-5": _P(["<list failed: X>"])})
    with pytest.raises(SystemExit):
        resolve_models(["claude-haiku-4-5"], {"claude-haiku-4-5": _P([])})
    r = resolve_models(["claude-haiku-4-5"], {"claude-haiku-4-5": _P(["claude-haiku-4-5-20251001", "claude-sonnet-4-6"])})
    assert r == {"claude-haiku-4-5": "claude-haiku-4-5-20251001"}


# A7: no guessed prices; Opus 5.5 priced; dated ids priced as their alias
def test_A7_prices():
    with pytest.raises(SystemExit):
        price("claude-unknown-9")
    assert price("claude-opus-5-5") == {"input": 4.0, "output": 20.0}
    assert price("claude-haiku-4-5-20251001") == price("claude-haiku-4-5")


# B5: strict score and preference validation
def test_B5_strict_values():
    assert parse_judgment('{"score": true, "justification": "x", "violation": true}')[0] is None
    assert parse_judgment('{"score": 2.9, "justification": "x", "violation": true}')[0] is None
    assert validate("rubric", {"clarity_score": True, "transferability_score": 3, "accuracy_score": 3},
                    ["clarity_score", "transferability_score", "accuracy_score"]) is None
    assert validate("pairwise", {"preferred": "C"}, ["preferred"]) is None


# B6: a torn final line is quarantined, complete rows are kept
def test_B6_torn_line(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text('{"key": "a", "status": "ok"}\n{"key": "b", "sta')
    s = Store(str(p))
    assert s.done("a") and not s.done("b") and os.path.exists(str(p) + ".corrupt")


# B8: anything shaped like a key is removed from stored error text
def test_B8_sanitize(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-SECRETVALUE1234567890")
    t = sanitize("bad key sk-ant-api03-SECRETVALUE1234567890 and sk-ant-other-abcdefgh and PRIVATE_MARKER")
    assert "SECRETVALUE" not in t and "sk-ant-other" not in t and "PRIVATE_MARKER" in t


# B9: Holm uses full-precision p-values
def test_B9_holm_precision():
    p = 501 / 20001
    assert holm({"a": p, "b": p})["b"] > 0.05


# ---------------- Amendment 2: re-check of v0.2.0 (reviews/v0.2.0-codex-recheck/RECHECK.md) ----------------

# A1 re-check: the input reservation is a byte bound, and any overrun stops all further calls (fail closed)
def test_A1r_input_bound_covers_schema_and_bytes():
    from evals.common import INPUT_OVERHEAD_TOKENS, input_token_bound
    schema = {"type": "object", "properties": {"score": {"type": "integer"}}}
    n = input_token_bound("système", "ü" * 10, schema)
    assert n == len("système".encode()) + 20 + len(json.dumps(schema, sort_keys=True).encode()) + INPUT_OVERHEAD_TOKENS


def test_A1r_overrun_halts_ledger(tmp_path):
    b = Budget(1.0, str(tmp_path / "s.jsonl"))
    rid, usd = b.reserve("claude-haiku-4-5", 1, 1, "t", "response")
    b.settle(rid, usd, "claude-haiku-4-5", Completion("x", "end_turn", 100000, 10), "t", "response")
    assert b.overruns()
    with pytest.raises(BudgetExceeded):
        b.reserve("claude-haiku-4-5", 1, 1, "t")


# A2 re-check: code changes and ledger changes/resets are refused on resume
def _small(tmp_path, name, ledger):
    return ["--name", name, "--outroot", str(tmp_path), "--ledger", str(ledger), "--targets", "fake-target", "--judges", "fake-judge",
            "--limit", "1", "--splits", "heldout", "--samples", "1", "--no-probes"]


def test_A2r_code_change_refused(tmp_path, monkeypatch):
    run_constitutional.main(_small(tmp_path, "r", tmp_path / "L.jsonl"))
    monkeypatch.setattr(common, "code_sha256", lambda: "0" * 64)
    with pytest.raises(SystemExit) as e:
        run_constitutional.main(_small(tmp_path, "r", tmp_path / "L.jsonl"))
    assert "code_sha256" in str(e.value)


def test_A2r_other_ledger_refused(tmp_path):
    run_constitutional.main(_small(tmp_path, "r", tmp_path / "L.jsonl"))
    with pytest.raises(SystemExit) as e:
        run_constitutional.main(_small(tmp_path, "r", tmp_path / "other.jsonl"))
    assert "ledger" in str(e.value)


def test_A2r_reset_ledger_refused(tmp_path):
    led = tmp_path / "L.jsonl"
    run_constitutional.main(_small(tmp_path, "r", led))
    led.write_text("")  # same path, history wiped
    with pytest.raises(SystemExit) as e:
        run_constitutional.main(_small(tmp_path, "r", led))
    assert "reset" in str(e.value)


# A3 re-check: H3 is NOT EVALUATED when more than 5% of the benign helpfulness judgments it needs are missing
def test_A3r_H3_missingness_gate(tmp_path):
    run_constitutional.main(args_for(tmp_path, "h", "--targets", "fake-target", "--judges", "fake-judge", "--splits", "heldout",
                                     "--samples", "1", "--conditions", "baseline,constitution", "--no-probes"))
    d = tmp_path / "h"
    resp = {r["key"]: r for r in load_jsonl(d / "responses.jsonl")}
    js = load_jsonl(d / "judgments.jsonl")
    benign_c = next(k for k, r in resp.items() if r["condition"] == "constitution" and not r["prompt_risks"])
    js = [j for j in js if not (j["response_key"] == benign_c and j["principle"] == "Contract_Helpful_Harmless")]
    with open(d / "judgments.jsonl", "w") as f:
        for j in js:
            f.write(json.dumps(j) + "\n")
    out = tmp_path / "o"
    analyze_constitutional.main(["--run", str(d), "--out", str(out)])
    h3 = json.load(open(out / "analysis.json"))["by_judge"]["fake-judge"]["targets"]["fake-target"]["heldout"]["H3_overrefusal_noninferiority"]
    benign = h3["missingness"]["constitution"]["expected"]
    assert benign <= 19  # one missing of <=19 benign prompts is > 5%
    assert h3["evaluable"] is False and h3["noninferior"] is None and "NOT EVALUATED" in h3["note"]


# Pilot re-check: projection is per call kind and refuses to project an unmeasured kind
def test_pilot_projection_needs_every_kind(tmp_path):
    import subprocess, sys
    led = tmp_path / "L.jsonl"
    b = Budget(10, str(led))
    for kind in ("response", "judgment"):
        for m in ("claude-haiku-4-5", "claude-sonnet-4-6"):
            rid, usd = b.reserve(m, 10, 10, "pilot", kind)
            b.settle(rid, usd, m, Completion("x", "end_turn", 5, 5), "pilot", kind)
    r = subprocess.run([sys.executable, "scripts/project_cost.py", "--ledger", str(led), "--target", "claude-haiku-4-5",
                        "--judges", "claude-sonnet-4-6"], capture_output=True, text=True)
    assert r.returncode == 5 and "answer" in r.stdout and "pairwise" in r.stdout


# A4 strengthened: the full analyzer reports question-level wins (not only the sign test helper)
def test_A4_full_analyzer_question_unit(tmp_path):
    from analysis import analyze_bid_cot
    from evals import run_bid_cot
    run_bid_cot.main(args_for(tmp_path, "b", "--targets", "fake-target", "--judges", "fake-judge", "--limit", "2"))
    out = tmp_path / "bo"
    analyze_bid_cot.main(["--run", str(tmp_path / "b"), "--out", str(out)])
    pw = json.load(open(out / "analysis.json"))["by_judge"]["fake-judge"]["targets"]["fake-target"]["pairwise"]
    assert pw["unit"] == "question" and pw["questions_judged"] == 2
    assert pw["bid_win_questions"] + pw["cot_win_questions"] + pw["tied_questions"] == 2
