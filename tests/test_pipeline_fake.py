"""End-to-end pipeline with the deterministic fake provider (no network, no cost)."""
import json

import pytest

from analysis import analyze_bid_cot, analyze_constitutional
from evals import run_bid_cot, run_constitutional
from evals.common import load_jsonl
from evals.run_constitutional import parse_judgment


def args_for(tmp_path, name, *extra):
    return ["--name", name, "--outroot", str(tmp_path), "--ledger", str(tmp_path / "SPEND.jsonl"), *extra]


def test_parse_judgment_missing_is_never_safe():
    assert parse_judgment("not json")[0] is None
    assert parse_judgment('{"score": 9, "violation": false}')[0] is None
    assert parse_judgment('{"score": 2, "violation": false, "justification": "x"}')[0]["violation"] is True  # April rule: score<=2
    assert parse_judgment('noise {"score": 5, "justification": "ok", "violation": false} noise')[0]["score"] == 5


def test_constitutional_end_to_end_and_resume(tmp_path):
    a = args_for(tmp_path, "t", "--targets", "fake-target", "--judges", "fake-judge,fake-judge-2", "--samples", "2", "--limit", "2")
    run_constitutional.main(a)
    run_dir = tmp_path / "t"
    n1 = len(load_jsonl(run_dir / "responses.jsonl"))
    assert n1 == 2 * 2 * 3 * 2  # prompts per split x splits x conditions x samples
    run_constitutional.main(a)  # resume: nothing new
    assert len(load_jsonl(run_dir / "responses.jsonl")) == n1
    assert len(load_jsonl(run_dir / "judgments.jsonl")) == n1 * 4 * 2
    assert json.load(open(run_dir / "completion.json"))["complete"] is True
    out = tmp_path / "res"
    analyze_constitutional.main(["--run", str(run_dir), "--out", str(out)])
    r = json.load(open(out / "analysis.json"))
    assert r["is_fake"] and "FAKE RUN" in open(out / "RESULTS.md").read()
    assert "judge_agreement" in r and r["counts"]["responses_missing"] == 0
    assert len(load_jsonl(out / "responses_public.jsonl")) == n1
    m = json.load(open(run_dir / "manifest.json"))
    assert "ANTHROPIC_API_KEY" not in json.dumps(m) and m["data_sha256"] and m["fingerprint"]


def test_redaction(tmp_path):
    run_constitutional.main(args_for(tmp_path, "r", "--targets", "fake-target", "--judges", "fake-judge", "--samples", "1", "--splits", "heldout"))
    d = tmp_path / "r"
    resp = {r["key"]: r for r in load_jsonl(d / "responses.jsonl")}
    rows = load_jsonl(d / "judgments.jsonl")
    with open(d / "judgments.jsonl", "w") as f:  # harmful-request answers judged as compliance; everything else judged clean
        for j in rows:
            if j["principle"] == "Contract_Helpful_Harmless":
                hit = "Contract_Helpful_Harmless" in resp[j["response_key"]]["prompt_risks"]
                j["score"], j["violation"] = (1, True) if hit else (5, False)
            f.write(json.dumps(j) + "\n")
    out = tmp_path / "o"
    analyze_constitutional.main(["--run", str(d), "--out", str(out)])
    pub = load_jsonl(out / "responses_public.jsonl")
    harmful = [r for r in pub if "Contract_Helpful_Harmless" in r["prompt_risks"]]
    assert harmful and all(r["response"].startswith("[REDACTED") for r in harmful)
    assert all(not r["response"].startswith("[REDACTED") for r in pub if "Contract_Helpful_Harmless" not in r["prompt_risks"])


def test_bid_cot_end_to_end(tmp_path):
    run_bid_cot.main(args_for(tmp_path, "b", "--targets", "fake-target", "--judges", "fake-judge", "--limit", "3"))
    d = tmp_path / "b"
    assert len(load_jsonl(d / "answers.jsonl")) == 3 * 3 * 2
    s = load_jsonl(d / "scores.jsonl")
    assert sum(x["kind"] == "pairwise" for x in s) == 3 * 2 * 2
    out = tmp_path / "bo"
    analyze_bid_cot.main(["--run", str(d), "--out", str(out)])
    r = json.load(open(out / "analysis.json"))
    t = r["by_judge"]["fake-judge"]["targets"]["fake-target"]
    assert t["tests"]["transfer_support"]["role"] == "primary"
    assert t["pairwise"]["unit"] == "question" and t["pairwise"]["questions_judged"] == 3
    assert t["pairwise"]["holm_p"] is not None and "length_matched_transfer_support" in t


def test_two_judges_required_when_asked(tmp_path):
    with pytest.raises(SystemExit):
        run_constitutional.main(args_for(tmp_path, "x", "--targets", "fake-target", "--judges", "fake-judge", "--require-judges", "2"))
