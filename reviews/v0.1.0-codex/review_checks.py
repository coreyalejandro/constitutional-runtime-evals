"""Independent offline probes. Run from the unmodified v0.1.0 clone. No credentials or network."""
import contextlib
import hashlib
import io
import json
import math
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch

assert not os.environ.get("ANTHROPIC_API_KEY")
assert not os.environ.get("OPENAI_API_KEY")
sys.path.insert(0, str(Path.cwd()))

def denied(*a, **kw):
    raise AssertionError("NETWORK DISALLOWED IN INDEPENDENT REVIEW")
socket.create_connection = denied
socket.socket.connect = denied

from evals import common as C, providers as P, run_constitutional as RC, run_bid_cot as RB
from analysis import analyze_constitutional as AC, analyze_bid_cot as AB
from analysis.stats import paired_permutation, bootstrap_mean_ci, holm, sign_test

root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
findings = {}

def record(name, value):
    findings[name] = value
    print(name + ": " + json.dumps(value, sort_keys=True))

def write_jsonl(p, rows):
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))

with tempfile.TemporaryDirectory(dir=root) as td:
    d = Path(td)
    s = C.Store(d / "store.jsonl")
    s.add({"key": "transport", "error": "timeout"})
    s.add({"key": "parse", "error": None, "parse_error": "unparseable", "score": None})
    s.add({"key": "success", "error": None, "score": 5})
    record("T01_store_retry", {k: s.has(k) for k in ("transport", "parse", "success")})
    s.add({"key": "transport", "error": None, "score": 4})
    record("T02_latest_row", {"physical_rows": len(C.load_jsonl(s.path)), "latest_rows": len(C.Store(s.path).latest()), "repaired_row_done": C.Store(s.path).has("transport")})
    with open(s.path, "a") as f:
        f.write('{"key":"partial')
    try:
        C.Store(s.path)
    except Exception as e:
        record("T03_partial_write", type(e).__name__)

    args = ["--name", "resume", "--targets", "fake-target", "--judges", "fake-judge", "--conditions", "baseline", "--splits", "heldout", "--limit", "1", "--samples", "2", "--outroot", str(d)]
    with contextlib.redirect_stdout(io.StringIO()):
        RC.main(args)
    rdir = d / "resume"
    before = json.loads((rdir / "manifest.json").read_text())
    args[args.index("--samples") + 1] = "1"
    args += ["--temperature", "0.25"]
    with patch.object(C, "git_head", return_value="synthetic-new-revision"), contextlib.redirect_stdout(io.StringIO()):
        RC.main(args)
    after = json.loads((rdir / "manifest.json").read_text())
    record("T04_resume_manifest", {"before_samples": before["config"]["samples"], "after_samples": after["config"]["samples"], "after_temperature": after["config"]["temperature"], "after_head": after["git_head"], "response_rows_kept": len(C.load_jsonl(rdir / "responses.jsonl")), "judgment_rows_kept": len(C.load_jsonl(rdir / "judgments.jsonl"))})

    response = {"key": "r"}
    js = [{"response_key": "r", "judge": "j", "principle": str(i), "violation": i == 0} for i in range(3)]
    v3 = AC.response_verdicts([response], js, "j")[0]["r"]
    js.append({"response_key": "r", "judge": "j", "principle": "3", "violation": None})
    v4 = AC.response_verdicts([response], js, "j")[0]["r"]
    js[0]["violation"] = False
    vm = AC.response_verdicts([response], js, "j")[0]["r"]
    record("T05_response_verdicts", {"violation_plus_absent_row": v3, "violation_plus_null_row": v4, "no_violation_plus_null_row": vm})
    record("T06_score_validation", {"boolean_constitution": RC.parse_judgment('{"score":true}')[0], "fractional_constitution": RC.parse_judgment('{"score":2.9}')[0], "boolean_bid_accepted": RB.valid_score(True)})

    bdir = d / "bid"
    bdir.mkdir()
    (bdir / "manifest.json").write_text(json.dumps({"started_utc": "synthetic", "git_head": "synthetic", "data_sha256": {}, "config": {"targets": "fake-target", "judges": "fake-judge"}}))
    answers, scores = [], []
    for k in range(2):
        for cond in ("plain", "cot", "bid"):
            key = f"fake-target|{cond}|Q01|{k}"
            answers.append({"key": key, "target": "fake-target", "condition": cond, "qid": "Q01", "domain": "test", "sample": k, "answer": "synthetic", "stop_reason": "end_turn", "output_tokens": 20})
            scores.append({"key": "transfer|" + key, "kind": "transfer", "judge": "fake-judge", "answer_key": key, "result": {"transfer_support_score": 5 if cond == "bid" else 3}})
            scores.append({"key": "rubric|" + key, "kind": "rubric", "judge": "fake-judge", "answer_key": key, "result": {"clarity_score": 5 if cond == "bid" else 3, "transferability_score": 5 if cond == "bid" else 3, "accuracy_score": 5 if cond == "bid" else 3}})
        for order in ("bid_first", "cot_first"):
            scores.append({"key": f"pair|{k}|{order}", "kind": "pairwise", "judge": "fake-judge", "target": "fake-target", "qid": "Q01", "sample": k, "order": order, "result": {"preferred": "A" if order == "bid_first" else "B"}})
    write_jsonl(bdir / "answers.jsonl", answers)
    write_jsonl(bdir / "scores.jsonl", scores)
    with contextlib.redirect_stdout(io.StringIO()):
        AB.main(["--run", str(bdir), "--out", str(d / "bout")])
    br = json.loads((d / "bout/analysis.json").read_text())["by_judge"]["fake-judge"]["targets"]["fake-target"]
    record("T07_bid_analysis", {"primary_n_questions": br["tests"]["transfer_support"]["n_questions"], "pairwise": br["pairwise"], "question_level_sign_p": sign_test(1, 0), "holm_corrected_names": [k for k, v in br["tests"].items() if "holm_p" in v], "pairwise_has_holm": "holm_p" in br["pairwise"], "length_matched_output": any("match" in k for k in br)})
    scores[-1]["result"]["preferred"] = "INVALID"
    write_jsonl(bdir / "scores.jsonl", scores)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            AB.main(["--run", str(bdir), "--out", str(d / "bad-pair")])
    except Exception as e:
        record("T08_invalid_pairwise", type(e).__name__)

    b = C.Budget(0.01, str(d / "budget.jsonl"))
    barrier = threading.Barrier(4)
    def job():
        b.check()
        barrier.wait()
        b.charge("claude-sonnet-4-6", 1000, 0)
    with contextlib.redirect_stdout(io.StringIO()):
        C.run_parallel([job] * 4, 4, "synthetic-budget")
    record("T09_budget", {"cap": b.max_usd, "spent": b.spent, "exceeded_without_stop": b.spent > b.max_usd})

    class BadRequest(Exception):
        status_code = 400
    class StubMessages:
        def __init__(self, fail=False):
            self.calls = []
            self.fail = fail
        def create(self, **kwargs):
            self.calls.append(dict(kwargs))
            if self.fail:
                raise BadRequest("synthetic server echoes PRIVATE_MARKER")
            if "extra_body" in kwargs:
                raise BadRequest("unsupported temperature")
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")], stop_reason="end_turn", usage=SimpleNamespace(input_tokens=2, output_tokens=3))
    stub = StubMessages()
    p = object.__new__(P.AnthropicProvider)
    p.client = SimpleNamespace(messages=stub)
    completion = p.complete("synthetic", "s", "u", 20, 0)
    record("T10_temperature", {"calls": len(stub.calls), "first_has_temperature": "extra_body" in stub.calls[0], "fallback_has_temperature": "extra_body" in stub.calls[1], "applied": completion.temperature_applied, "reported_attempts": completion.attempts})
    p.client = SimpleNamespace(messages=StubMessages(fail=True))
    error = p.complete("synthetic", "s", "u", 20, None)
    st = C.Store(d / "exception.jsonl")
    st.add({"key": "error", **error.to_dict()})
    record("T11_exception_storage", {"synthetic_marker_written": "PRIVATE_MARKER" in (d / "exception.jsonl").read_text(), "reported_attempts": error.attempts})

    class MissingList(P.FakeProvider):
        calls = 0
        def list_models(self):
            return ["<list failed: SyntheticFailure>"]
        def complete(self, *a, **kw):
            self.calls += 1
            return super().complete(*a, **kw)
    stubp = MissingList()
    with patch.object(RC, "providers_for", return_value=({"fake": stubp}, {"fake-target": stubp, "fake-judge": stubp})), contextlib.redirect_stdout(io.StringIO()):
        RC.main(["--name", "failed-list", "--targets", "fake-target", "--judges", "fake-judge", "--limit", "1", "--samples", "1", "--splits", "heldout", "--outroot", str(d)])
    record("T12_failed_model_list", {"completion_calls_despite_failed_list": stubp.calls})

    class DatedList(MissingList):
        def list_models(self):
            return ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]
    stubp = DatedList()
    try:
        with patch.object(RC, "providers_for", return_value=({"anthropic": stubp}, {"claude-haiku-4-5": stubp, "claude-sonnet-4-6": stubp})), contextlib.redirect_stdout(io.StringIO()):
            RC.main(["--name", "alias-list", "--targets", "claude-haiku-4-5", "--judges", "claude-sonnet-4-6", "--limit", "1", "--samples", "1", "--splits", "heldout", "--outroot", str(d)])
    except SystemExit as e:
        record("T13_alias_check", str(e))

    class Truncated(P.FakeProvider):
        def complete(self, *a, **kw):
            c = super().complete(*a, **kw)
            c.stop_reason = "max_tokens"
            return c
    tp = Truncated()
    with patch.object(RC, "providers_for", return_value=({"fake": tp}, {"fake-target": tp, "fake-judge": tp})), contextlib.redirect_stdout(io.StringIO()):
        RC.main(["--name", "truncated", "--targets", "fake-target", "--judges", "fake-judge", "--limit", "1", "--samples", "1", "--splits", "heldout", "--outroot", str(d)])
    tj = C.load_jsonl(d / "truncated/judgments.jsonl")
    tprobes = C.load_jsonl(d / "truncated/probes.jsonl")
    with patch.object(RB, "providers_for", return_value=({"fake": tp}, {"fake-target": tp, "fake-judge": tp})), contextlib.redirect_stdout(io.StringIO()):
        RB.main(["--name", "truncated-bid", "--targets", "fake-target", "--judges", "fake-judge", "--limit", "1", "--samples", "1", "--outroot", str(d)])
    ts = C.load_jsonl(d / "truncated-bid/scores.jsonl")
    record("T14_truncation", {"constitutional_null": sum(j["score"] is None for j in tj), "constitutional_total": len(tj), "probe_null": sum(j["score"] is None for j in tprobes), "probe_total": len(tprobes), "bid_null": sum(j["result"] is None for j in ts), "bid_total": len(ts)})

    # Minimal synthetic public export. No actual harmful answer is generated or printed.
    rr = {"key": "r", "target": "fake-target", "condition": "baseline", "prompt_id": "synthetic", "split": "heldout", "sample": 0, "prompt_risks": [], "query": "synthetic", "response": "SYNTHETIC_COMPLIANCE_MARKER", "stop_reason": "end_turn"}
    jjs = [{"key": f"r|fake-judge|{pr['name']}", "response_key": "r", "judge": "fake-judge", "principle": pr["name"], "score": 1 if pr["name"] == AC.HARM else 5, "violation": pr["name"] == AC.HARM} for pr in RC.AP.CONSTITUTION]
    rdir2 = d / "redaction"
    rdir2.mkdir()
    (rdir2 / "manifest.json").write_text(json.dumps({"started_utc": "synthetic", "git_head": "synthetic", "data_sha256": {}, "config": {"targets": "fake-target", "judges": "fake-judge", "conditions": "baseline"}}))
    write_jsonl(rdir2 / "responses.jsonl", [rr]); write_jsonl(rdir2 / "judgments.jsonl", jjs)
    with contextlib.redirect_stdout(io.StringIO()):
        AC.main(["--run", str(rdir2), "--out", str(d / "redacted-out")])
    untagged = C.load_jsonl(d / "redacted-out/responses_public.jsonl")[0]["response"]
    rr["prompt_risks"] = [AC.HARM]
    write_jsonl(rdir2 / "responses.jsonl", [rr])
    with contextlib.redirect_stdout(io.StringIO()):
        AC.main(["--run", str(rdir2), "--out", str(d / "redacted-tagged")])
    tagged = C.load_jsonl(d / "redacted-tagged/responses_public.jsonl")[0]["response"]
    record("T15_redaction", {"tagged_harmful_redacted": tagged.startswith("[REDACTED"), "untagged_harmful_kept": untagged == "SYNTHETIC_COMPLIANCE_MARKER", "sha256_correct": C.sha256_text(rr["response"]) in tagged})

record("T16_small_effect_detection", {str(p): sum(math.comb(50, k) * p**k * (1-p)**(50-k) for k in range(7, 51)) for p in (0.05, 0.1, 0.2)})
record("T17_h3_ceiling", {"all_zero_difference_ci": bootstrap_mean_ci([0] * 10), "one_point_drop_on_one_prompt_ci": bootstrap_mean_ci([-1] + [0]*9)})
record("T18_holm_rounding", {"unrounded_adjusted": holm({"H1": 0.02499, "H2": 0.02499}), "current_adjusted": holm({"H1": AC.r4(0.02499), "H2": AC.r4(0.02499)})})

archive = Path("archive/2026-04-tlc")
am = json.loads((archive / "ARCHIVE_MANIFEST.json").read_text())
mismatched = [f for f, h in am["files"].items() if hashlib.sha256((archive/f).read_bytes()).hexdigest() != h]
ho, dev = C.load_jsonl("data/heldout_prompts.jsonl"), C.load_jsonl("data/dev_prompts.jsonl")
from collections import Counter
record("T19_integrity", {"archive_files": len(am["files"]), "archive_hash_mismatches": mismatched, "heldout_strata": dict(Counter((r["prompt_risks"] or ["benign"])[0] for r in ho)), "exact_prompt_overlap": len({r["prompt"] for r in ho} & {r["prompt"] for r in dev}), "bid_domains": dict(Counter(r["domain"] for r in C.load_jsonl("data/bid_cot_questions.jsonl")))})

exposed = []
for file in sorted((archive / "runs").glob("*/report.json")):
    report = json.loads(file.read_text())
    for cond in ("baseline", "constitution_strategy"):
        for r in report[cond]["cases"]:
            if AC.HARM in r.get("detected_model_violations", r.get("detected_violations", [])) and r.get("response_full"):
                exposed.append({"file": str(file), "case_id": r.get("case_id"), "condition": cond, "response_sha256": C.sha256_text(r["response_full"])})
record("T20_archive_unredacted", {"rows_flagged_helpful_harmless_with_full_response": len(exposed), "locations": exposed})
record("T21_control_prompts", {"baseline": RC.AP.baseline_prompt("Q")[0], "generic_safety": RC.generic_safety_prompt("Q")[0], "constitution_header": RC.AP.constitution_prompt("Q")[0].split("\n")[0]})
(root / "checks.json").write_text(json.dumps(findings, indent=2) + "\n")
print("OFFLINE CHECKS COMPLETE; no real provider instantiated; no API key used; socket connections blocked.")
