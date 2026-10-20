"""Shared run infrastructure (v0.2.0, after independent review v0.1.0).

- Store: append-only JSONL keyed by 'key'; tolerant of a torn final line; bounded retries.
- RunLock: one process per run directory.
- Budget: one shared ledger across all runs; worst-case cost is RESERVED before each call
  (atomic across threads and processes) and settled after; unknown outcomes are charged in full.
- Manifest: written once; every later invocation must match its fingerprint or is refused.
- sanitize(): strips anything that looks like an API key from text before it is stored.
"""
from __future__ import annotations

import fcntl, hashlib, json, os, platform, re, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone

PRICING_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "pricing.json")
PRICING = json.load(open(PRICING_PATH))
MAX_ATTEMPTS = 3  # first try + 2 retries, for transport errors AND unparseable/invalid outputs


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def sha256_text(t):
    return hashlib.sha256((t or "").encode()).hexdigest()


_KEY_PATTERNS = [re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), re.compile(r"sk-[A-Za-z0-9_\-]{20,}")]


def sanitize(text):
    """Remove anything shaped like an API key, and the literal values of key env vars, from text."""
    if not text:
        return text
    out = str(text)
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        v = os.environ.get(var)
        if v and len(v) >= 8:
            out = out.replace(v, "[REDACTED_KEY]")
    for p in _KEY_PATTERNS:
        out = p.sub("[REDACTED_KEY]", out)
    return out


def load_jsonl(p, quarantine=True):
    """Read JSONL. Unparseable lines (e.g. a torn final write) are moved to <file>.corrupt, never silently used."""
    if not os.path.exists(p):
        return []
    rows, bad = [], []
    with open(p, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad.append(line)
    if bad and quarantine:
        with open(p + ".corrupt", "a", encoding="utf-8") as f:
            f.writelines(bad)
        with open(p, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"WARNING: {len(bad)} unreadable line(s) in {p} moved to {p}.corrupt", file=sys.stderr)
    return rows


class Store:
    """Append-only JSONL keyed by 'key'. A key is DONE when its latest row has status 'ok', or when it has
    used MAX_ATTEMPTS attempts (then it is final-missing and reported as such)."""

    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.rows, self.attempt_count = {}, {}
        for r in load_jsonl(path):
            self.rows[r["key"]] = r
            self.attempt_count[r["key"]] = self.attempt_count.get(r["key"], 0) + 1
        self.lock = threading.Lock()

    def done(self, key):
        r = self.rows.get(key)
        return r is not None and (r.get("status") == "ok" or self.attempt_count.get(key, 0) >= MAX_ATTEMPTS)

    def attempts(self, key):
        return self.attempt_count.get(key, 0)

    def add(self, row):
        with self.lock:
            self.attempt_count[row["key"]] = self.attempt_count.get(row["key"], 0) + 1
            row["attempt"] = self.attempt_count[row["key"]]
            self.rows[row["key"]] = row
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def latest(self):
        return list(self.rows.values())


class RunLock:
    """Refuse a second process writing the same run directory."""

    def __init__(self, outdir):
        self.f = open(os.path.join(outdir, ".lock"), "w")
        try:
            fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(f"Another process is already writing {outdir}. Stop it first.")


def price(model):
    base = re.sub(r"-\d{8}$", "", model)  # a dated snapshot id is priced as its alias
    if model not in PRICING and base in PRICING:
        model = base
    if model not in PRICING or model.startswith("_"):
        raise SystemExit(f"No price for model '{model}' in config/pricing.json. Add the official price before running "
                         f"(the run refuses to guess).")
    return PRICING[model]


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    """Shared spend ledger with atomic worst-case reservation (threads + processes).

    Every call reserves (input_estimate * input_price + max_output_tokens * output_price) before it is sent.
    The reservation is refused if spent + open reservations + this reservation would pass the cap.
    After the call, the reservation is settled at the actual usage; a call whose outcome is unknown
    (exception, timeout) is charged the full reservation, marked 'charged_unknown'.
    This is a LOCAL guard. The provider's own hard limit is the prepaid credit balance (auto-reload off).
    """

    def __init__(self, max_usd, ledger_path):
        self.max_usd, self.path = max_usd, ledger_path
        os.makedirs(os.path.dirname(ledger_path) or ".", exist_ok=True)
        self.lockpath = ledger_path + ".lock"
        self.tlock = threading.Lock()

    @contextmanager
    def _plock(self):
        with self.tlock, open(self.lockpath, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)

    def _ledger(self):
        return load_jsonl(self.path, quarantine=False)

    def spent(self):
        return sum(r["usd"] for r in self._ledger() if r.get("type") in ("settled", "charged_unknown"))

    def _open_reserved(self):
        rows = self._ledger()
        res = {r["rid"]: r["usd"] for r in rows if r.get("type") == "reserve"}
        for r in rows:
            if r.get("type") in ("settled", "charged_unknown"):
                res.pop(r.get("rid"), None)
        return sum(res.values())

    def _write(self, row):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def overruns(self):
        return [r for r in self._ledger() if r.get("type") == "overrun"]

    def reserve(self, model, input_tokens_bound, max_output_tokens, run, kind=None):
        p = price(model)
        usd = (input_tokens_bound * p["input"] + max_output_tokens * p["output"]) / 1e6
        with self._plock():
            if self.overruns():
                raise BudgetExceeded("a past call cost more than its reservation (see 'overrun' rows in the ledger); "
                                     "no new calls until the owner reviews it")
            committed = self.spent() + self._open_reserved()
            if committed + usd > self.max_usd:
                raise BudgetExceeded(f"budget cap ${self.max_usd:.2f}: committed ${committed:.4f} + next call up to ${usd:.4f}")
            rid = hashlib.sha256(f"{now()}{threading.get_ident()}{os.getpid()}{model}{usd}{os.urandom(8).hex()}".encode()).hexdigest()[:16]
            self._write({"type": "reserve", "rid": rid, "at": now(), "run": run, "model": model, "kind": kind,
                         "usd": round(usd, 6)})
        return rid, usd

    def settle(self, rid, reserved_usd, model, completion, run, kind=None):
        p = price(model)
        with self._plock():
            if completion is None or (completion.error and completion.input_tokens == 0 and completion.output_tokens == 0):
                self._write({"type": "charged_unknown", "rid": rid, "at": now(), "run": run, "model": model, "kind": kind,
                             "usd": round(reserved_usd, 6), "note": "outcome unknown or failed; charged the full reservation"})
            else:
                usd = (completion.input_tokens * p["input"] + completion.output_tokens * p["output"]) / 1e6
                self._write({"type": "settled", "rid": rid, "at": now(), "run": run, "model": model, "kind": kind,
                             "in": completion.input_tokens, "out": completion.output_tokens, "usd": round(usd, 6)})
                if usd > reserved_usd + 1e-12:
                    self._write({"type": "overrun", "rid": rid, "at": now(), "run": run, "model": model, "kind": kind,
                                 "reserved_usd": round(reserved_usd, 6), "actual_usd": round(usd, 6)})
                    print(f"STOP: a {model} call cost ${usd:.6f}, more than its ${reserved_usd:.6f} reservation. "
                          f"No new calls will start.", file=sys.stderr, flush=True)

    def run_has_spend(self, run):
        return any(r.get("run") == run for r in self._ledger())


INPUT_OVERHEAD_TOKENS = 2048  # message framing + structured-output scaffolding the provider adds (Amendment 2)


def input_token_bound(*parts):
    """Worst-case input tokens (Amendment 2, review A1-recheck). Byte-level tokenizers never emit a token shorter than
    one byte, so the UTF-8 byte count of everything sent (system, user, output schema) bounds the token count; a fixed
    allowance covers framing the provider adds. If a call ever uses more than its reservation, settle() records an
    overrun and the ledger refuses all further calls until the owner decides (fail closed)."""
    n = 0
    for t in parts:
        if t is None:
            continue
        n += len((t if isinstance(t, str) else json.dumps(t, sort_keys=True)).encode("utf-8"))
    return n + INPUT_OVERHEAD_TOKENS


est_tokens = input_token_bound  # backward-compatible name


def run_parallel(jobs, workers, label):
    """jobs: zero-arg callables. On BudgetExceeded, in-flight calls finish and settle; nothing new starts."""
    done = 0
    stop = threading.Event()

    def wrap(j):
        if stop.is_set():
            return "skipped"
        try:
            return j()
        except BudgetExceeded as e:
            stop.set()
            return e

    budget_err = None
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(wrap, j) for j in jobs]
        for f in as_completed(futs):
            r = f.result()
            if isinstance(r, BudgetExceeded):
                budget_err = budget_err or r
            done += 1
            if done % 50 == 0 or done == len(jobs):
                print(f"  {label}: {done}/{len(jobs)}", flush=True)
    if budget_err:
        print(f"STOPPED: {budget_err}. Nothing new was started after this. Re-run with a higher --max-usd only if the owner approves.", flush=True)
        raise budget_err


def git_head():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _version(md, pkg):
    try:
        return md.version(pkg)
    except Exception:
        return None


CODE_DIRS = ("evals", "config")


def code_sha256():
    """Hash of the executable run code and config (evals/*.py, config/*). Amendment 2: a resume with different code is refused."""
    root = os.path.join(os.path.dirname(__file__), "..")
    h = hashlib.sha256()
    for d in CODE_DIRS:
        for f in sorted(os.listdir(os.path.join(root, d))):
            fp = os.path.join(root, d, f)
            if os.path.isfile(fp) and (f.endswith(".py") or f.endswith(".json")):
                h.update(f"{d}/{f}".encode()); h.update(open(fp, "rb").read())
    return h.hexdigest()


def manifest(outdir, cfg, fingerprint_fields, providers, data_files, resolved_models, budget=None, run_name=None):
    """Write manifest.json once. Later invocations must match its fingerprint, or the run is refused.
    The fingerprint covers settings, data hashes, resolved snapshots, prices, the run code hash and the ledger path."""
    import importlib.metadata as md
    data = {f: sha256_file(f) for f in data_files}
    fp_src = {"config": {k: cfg[k] for k in fingerprint_fields}, "data_sha256": data, "resolved_models": resolved_models,
              "pricing": {m: price(m) for m in resolved_models}, "code_sha256": code_sha256(),
              "ledger": os.path.relpath(os.path.realpath(budget.path)) if budget else None}
    fingerprint = hashlib.sha256(json.dumps(fp_src, sort_keys=True).encode()).hexdigest()
    path = os.path.join(outdir, "manifest.json")
    inv = {"at": now(), "git_head": git_head(), "python": sys.version.split()[0], "argv": sys.argv[1:]}
    if os.path.exists(path):
        old = json.load(open(path))
        if old.get("fingerprint") != fingerprint:
            changed = [k for k in fp_src if old.get(k) != fp_src[k]] if all(k in old for k in fp_src) else ["(older manifest format)"]
            raise SystemExit(f"Refusing to resume {outdir}: {', '.join(changed)} differ(s) from the original run "
                             f"(fingerprint {old.get('fingerprint', '')[:12]} vs {fingerprint[:12]}). Use a new --name.")
        made_calls = any(os.path.getsize(os.path.join(outdir, f)) > 0 for f in os.listdir(outdir)
                         if f.endswith(".jsonl") and f != "invocations.jsonl")
        if budget is not None and made_calls and not budget.run_has_spend(run_name):
            raise SystemExit(f"Refusing to resume {outdir}: it has recorded calls but the ledger {budget.path} has no spend rows for "
                             f"run '{run_name}'. The ledger looks reset or replaced, so earlier spend would escape the cap.")
        m = old
    else:
        m = {"created_utc": now(), "git_head": git_head(), "fingerprint": fingerprint, **fp_src, "config_full": cfg,
             "platform": platform.platform(),
             "available_models": {fam: p.list_models() for fam, p in providers.items()},
             "packages": {k: _version(md, k) for k in ("anthropic", "openai")}}
        json.dump(m, open(path, "w"), indent=2)
    with open(os.path.join(outdir, "invocations.jsonl"), "a") as f:
        f.write(json.dumps(inv) + "\n")
    return m


def resolve_models(models, providers_by_model):
    """Map each requested model to the exact snapshot the provider lists. Fails closed if the list can't be read.
    An alias like 'claude-haiku-4-5' resolves to the single listed id that equals it or starts with it + '-'."""
    out = {}
    for m in models:
        listed = providers_by_model[m].list_models()
        if not listed or any(str(x).startswith("<") for x in listed):
            raise SystemExit(f"Could not read the provider's model list for {m}; refusing to run without checking the model.")
        if m in listed:
            out[m] = m
            continue
        cands = sorted(x for x in listed if x.startswith(m + "-"))
        if len(cands) != 1:
            raise SystemExit(f"Model '{m}' is not uniquely available (matches: {cands}). Available: {listed[:40]}")
        out[m] = cands[0]
    return out


def interleave(jobs, seed):
    """Fixed-seed shuffle so conditions are spread evenly in time (independent review B11)."""
    import random
    jobs = list(jobs)
    random.Random(seed).shuffle(jobs)
    return jobs
