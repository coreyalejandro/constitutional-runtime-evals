"""Additional offline checks after initial findings; no real providers or credentials."""
import contextlib, io, json, os, runpy, socket, sys, tempfile
from pathlib import Path
from unittest.mock import patch
assert not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("OPENAI_API_KEY")
sys.path.insert(0, str(Path.cwd()))
def denied(*a, **k): raise AssertionError("NO NETWORK")
socket.create_connection = denied
socket.socket.connect = denied
from evals import common as C, providers as P, run_constitutional as RC
from analysis import analyze_constitutional as AC
from analysis.stats import holm
root = Path(sys.argv[1]).resolve()
records = {}
def record(name, v):
    records[name] = v
    print(name + ": " + json.dumps(v, sort_keys=True))
with tempfile.TemporaryDirectory(dir=root) as td:
    d=Path(td)
    class Failing(P.FakeProvider):
        def complete(self,*args,**kw): return P.Completion("", None, 0, 0, "synthetic failure")
    f=Failing()
    stdout=io.StringIO()
    with patch.object(RC,"providers_for",return_value=({"fake":f},{"fake-target":f,"fake-judge":f})),contextlib.redirect_stdout(stdout):
        RC.main(["--name","all-error","--targets","fake-target","--judges","fake-judge","--splits","heldout","--limit","1","--samples","1","--outroot",str(d)])
    record("X01_all_errors_success",{"done_printed": "Done. Spent" in stdout.getvalue(),"response_errors":sum(bool(r["error"]) for r in C.load_jsonl(d/"all-error/responses.jsonl")),"judgments":len(C.load_jsonl(d/"all-error/judgments.jsonl")),"runner_raised":False})
    # Single-provider timeouts can represent completed, billed requests with unobservable usage.
    record("X02_error_charge",{"error_completion_input_tokens":f.complete().input_tokens,"error_completion_output_tokens":f.complete().output_tokens})
v=501/20001
record("X03_holm_rounding",{"attainable_raw_p":v,"holm_without_prerounding":holm({"H1":v,"H2":v}),"holm_with_prerounding":holm({"H1":AC.r4(v),"H2":AC.r4(v)})})

# Cost estimates are arithmetic only. Do not select a judge, edit config, or call any API.
def estimates():
    ss=io.StringIO()
    with contextlib.redirect_stdout(ss):
        for exp,judges,samples in (("constitutional","claude-sonnet-4-6,claude-opus-5-5",3),("constitutional","claude-sonnet-4-6",1),("bid_cot","claude-sonnet-4-6,claude-opus-5-5",2)):
            with patch.object(sys,"argv",["scripts/estimate.py","--experiment",exp,"--judges",judges,"--samples",str(samples)]):
                runpy.run_path("scripts/estimate.py",run_name="__main__")
    return ss.getvalue()
record("X04_estimate_current_config",estimates())
with patch.dict(C.PRICING,{"claude-opus-5-5":{"input":4.0,"output":20.0}}):
    record("X05_estimate_verified_opus_price",estimates())
(root/"extra_checks.json").write_text(json.dumps(records,indent=2)+"\n")
