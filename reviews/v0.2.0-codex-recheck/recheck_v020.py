"""v0.2.0 re-check probes. No credentials or network. No repository code edits."""
import contextlib, io, json, os, socket, sys, tempfile, threading
from pathlib import Path
from unittest.mock import patch
assert not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("OPENAI_API_KEY")
sys.path.insert(0, str(Path.cwd()))
def denied(*a, **k): raise AssertionError("NETWORK DISALLOWED")
socket.create_connection=denied
socket.socket.connect=denied
from evals import common as C, providers as P, run_constitutional as RC, run_bid_cot as RB
from analysis import analyze_constitutional as AC, analyze_bid_cot as AB
output=Path(sys.argv[1]).resolve()
output.mkdir(parents=True,exist_ok=True)
obs={}
def record(k,v):
    obs[k]=v
    print(k+": "+json.dumps(v,sort_keys=True))
def quiet(fn,args):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(args)
def write_rows(p,rows):
    p.write_text("".join(json.dumps(r)+"\n" for r in rows))
with tempfile.TemporaryDirectory(dir=output) as td:
    d=Path(td)
    # A1: reserve concurrently through different Budget instances sharing the ledger.
    ledger=str(d/"concurrent.jsonl")
    ok=[]; refused=[]; barrier=threading.Barrier(8)
    def worker():
        b=C.Budget(.01,ledger)
        barrier.wait()
        try: ok.append(b.reserve("claude-sonnet-4-6",0,200,"synthetic"))
        except C.BudgetExceeded: refused.append(1)
    ts=[threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    b=C.Budget(.01,ledger)
    b.settle(ok[0][0],ok[0][1],"claude-sonnet-4-6",None,"synthetic")
    record("A1_atomic",{"accepted":len(ok),"refused":len(refused),"spent_unknown":b.spent(),"open_reserved":b._open_reserved()})
    b=C.Budget(.001,str(d/"underestimated.jsonl"))
    rid,res=b.reserve("claude-haiku-4-5",0,10,"synthetic")
    b.settle(rid,res,"claude-haiku-4-5",P.Completion("x","end_turn",2000,10),"synthetic")
    record("A1_underestimate",{"cap":.001,"reserved":res,"settled":b.spent(),"over_cap":b.spent()>.001})
    # A2: same code settings refused; code revision and ledger changes still accepted.
    base=["--name","resume","--targets","fake-target","--judges","fake-judge","--conditions","baseline","--splits","heldout","--limit","1","--samples","2","--no-probes","--outroot",str(d),"--ledger",str(d/"first-ledger.jsonl")]
    quiet(RC.main,base)
    mpath=d/"resume/manifest.json"
    original=mpath.read_bytes()
    changed=base.copy(); changed[changed.index("--samples")+1]="1"
    try: quiet(RC.main,changed); refused_settings=False
    except SystemExit: refused_settings=True
    preserved=mpath.read_bytes()==original
    with patch.object(C,"git_head",return_value="SYNTHETIC_NEW_CODE_REVISION"):
        quiet(RC.main,base)
    changed_ledger=base.copy()
    changed_ledger[changed_ledger.index("--ledger")+1]=str(d/"different-ledger.jsonl")
    quiet(RC.main,changed_ledger)
    invocations=C.load_jsonl(d/"resume/invocations.jsonl")
    record("A2_resume",{"changed_samples_refused":refused_settings,"initial_manifest_preserved":preserved,"changed_code_revision_accepted":any(r["git_head"]=="SYNTHETIC_NEW_CODE_REVISION" for r in invocations),"changed_ledger_accepted":True,"original_ledger":json.loads(mpath.read_text())["config_full"]["ledger"],"later_ledger":changed_ledger[changed_ledger.index("--ledger")+1]})
    # A3: known positive persists, null stays missing; retries bounded.
    r=[{"key":"r"}]
    j=[{"judge":"j","response_key":"r","principle":"one","status":"ok","violation":True}]
    v_absent=AC.response_verdicts(r,j,"j")[0]["r"]
    j.append({"judge":"j","response_key":"r","principle":"two","status":"invalid","violation":None})
    v_invalid=AC.response_verdicts(r,j,"j")[0]["r"]
    s=C.Store(str(d/"retry.jsonl"))
    s.add({"key":"k","status":"invalid"})
    once=s.done("k")
    s.add({"key":"k","status":"invalid"});s.add({"key":"k","status":"invalid"})
    record("A3_verdict_retry",{"known_violation_absent":v_absent,"known_violation_invalid":v_invalid,"done_after_one_invalid":once,"done_after_three_invalid":s.done("k")})
    class Failed(P.FakeProvider):
        def complete(self,*a,**k):return P.Completion("",None,0,0,"synthetic timeout")
    f=Failed()
    args=["--name","failed","--targets","fake-target","--judges","fake-judge","--splits","heldout","--limit","1","--samples","1","--no-probes","--outroot",str(d),"--ledger",str(d/"error-ledger.jsonl")]
    try:
        with patch.object(RC,"providers_for",return_value=({"fake":f},{"fake-target":f,"fake-judge":f})):
            quiet(RC.main,args)
        status=0
    except SystemExit as e:status=e.code
    completion=json.loads((d/"failed/completion.json").read_text())
    record("A3_failed_gate",{"exit":status,"complete":completion["complete"],"responses":completion["responses"],"attempt_rows":len(C.load_jsonl(d/"failed/responses.jsonl"))})
    # H3: 1/10 benign helpfulness judgments missing, all other records valid.
    hd=d/"h3";hd.mkdir()
    cfg={"targets":"fake-target","judges":"fake-judge","conditions":"baseline,generic_safety,constitution","splits":"heldout","limit":0,"samples":1}
    man={"created_utc":"synthetic","git_head":"synthetic","config_full":cfg,"resolved_models":{"fake-target":"fake-target","fake-judge":"fake-judge"}}
    (hd/"manifest.json").write_text(json.dumps(man))
    responses=[];judgments=[]
    for prompt in C.load_jsonl("data/heldout_prompts.jsonl"):
        for cond in cfg["conditions"].split(","):
            key=f"fake-target|{cond}|{prompt['id']}|0"
            row={"key":key,"target":"fake-target","condition":cond,"prompt_id":prompt["id"],"split":"heldout","sample":0,"prompt_risks":prompt["prompt_risks"],"query":prompt["prompt"],"response":"SYNTHETIC","response_sha256":C.sha256_text("SYNTHETIC"),"status":"ok","stop_reason":"end_turn"}
            responses.append(row)
            for principle in RC.AP.CONSTITUTION:
                if prompt["id"]=="HO-041" and cond=="constitution" and principle["name"]==AC.HARM:continue
                judgments.append({"key":f"{key}|fake-judge|{principle['name']}","response_key":key,"response_sha256":row["response_sha256"],"judge":"fake-judge","principle":principle["name"],"status":"ok","score":5,"violation":False})
    write_rows(hd/"responses.jsonl",responses);write_rows(hd/"judgments.jsonl",judgments)
    quiet(AC.main,["--run",str(hd),"--out",str(d/"h3-out")])
    ha=json.loads((d/"h3-out/analysis.json").read_text())
    hs=ha["by_judge"]["fake-judge"]["targets"]["fake-target"]["heldout"]
    record("A3_H3_missing",{"missing_benign_helpfulness_fraction":.1,"overall_constitution_verdict_missing_fraction":ha["missingness"]["fake-judge|fake-target|heldout"]["constitution"]["missing_fraction"],"H3":hs["H3_overrefusal_noninferiority"]})
    # A4: one question, two consistent BID sample wins, equal lengths.
    args=["--name","bid","--targets","fake-target","--judges","fake-judge","--limit","1","--samples","2","--outroot",str(d),"--ledger",str(d/"bid-ledger.jsonl")]
    quiet(RB.main,args)
    bd=d/"bid"
    answers=C.load_jsonl(bd/"answers.jsonl");scores=C.load_jsonl(bd/"scores.jsonl")
    for a in answers:a["output_tokens"]=20
    for sc in scores:
        if sc["kind"]=="pairwise":sc["result"]["preferred"]="A" if sc["order"]=="bid_first" else "B"
    write_rows(bd/"answers.jsonl",answers);write_rows(bd/"scores.jsonl",scores)
    quiet(AB.main,["--run",str(bd),"--out",str(d/"bid-out")])
    ba=json.loads((d/"bid-out/analysis.json").read_text())["by_judge"]["fake-judge"]["targets"]["fake-target"]
    record("A4_bid",{"pairwise":ba["pairwise"],"length_matched":ba["length_matched_transfer_support"],"primary_n_questions":ba["tests"]["transfer_support"]["n_questions"]})
    g=RC.generic_safety_prompt("Q")[0];c=RC.AP.constitution_prompt("Q")[0]
    strip=lambda p:"\n".join(l for l in p.splitlines() if not l.startswith("- "))
    record("A5_control",{"non_rule_text_identical":strip(g)==strip(c),"generic_bullets":sum(l.startswith("- ") for l in g.splitlines()),"constitution_bullets":sum(l.startswith("- ") for l in c.splitlines()),"role_line":g.splitlines()[0]})
    class Listed:
        def __init__(self,ls):self.ls=ls
        def list_models(self):return self.ls
    failed=[]
    for ls in ([],["<list failed: X>"]):
        try:C.resolve_models(["claude-haiku-4-5"],{"claude-haiku-4-5":Listed(ls)});failed.append(False)
        except SystemExit:failed.append(True)
    resolved=C.resolve_models(["claude-haiku-4-5"],{"claude-haiku-4-5":Listed(["claude-haiku-4-5-20251001","claude-sonnet-4-6"])})
    record("A6_models",{"empty_and_failed_lists_refused":failed,"resolved":resolved})
    try:C.price("unknown-model");unknown=False
    except SystemExit:unknown=True
    record("A7_prices",{"haiku":C.price("claude-haiku-4-5"),"dated_haiku":C.price("claude-haiku-4-5-20251001"),"sonnet":C.price("claude-sonnet-4-6"),"opus55":C.price("claude-opus-5-5"),"unknown_refused":unknown})
(output/"RECHECK_PROBE_RESULTS.json").write_text(json.dumps(obs,indent=2)+"\n")
print("RECHECK PROBES COMPLETE: fake providers only; no real keys; sockets blocked.")

