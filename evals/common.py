"""Shared run infrastructure: resumable JSONL stores, a hard budget guard, run manifests."""
from __future__ import annotations

import hashlib, json, os, platform, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

PRICING = json.load(open(os.path.join(os.path.dirname(__file__), "..", "config", "pricing.json")))


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def sha256_text(t):
    return hashlib.sha256(t.encode()).hexdigest()


def load_jsonl(p):
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


class Store:
    """Append-only JSONL keyed by 'key'. Re-running skips keys already present (resume after a crash)."""

    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.rows = {r["key"]: r for r in load_jsonl(path)}
        self.lock = threading.Lock()

    def has(self, key):
        r = self.rows.get(key)
        return r is not None and not r.get("error")  # errored rows are retried on the next run

    def add(self, row):
        with self.lock:
            self.rows[row["key"]] = row
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def latest(self):
        return list(self.rows.values())


def price(model):
    return PRICING.get(model, PRICING["_default"])


class Budget:
    def __init__(self, max_usd, ledger_path):
        self.max_usd, self.path, self.lock = max_usd, ledger_path, threading.Lock()
        self.spent = sum(r["usd"] for r in load_jsonl(ledger_path))

    def charge(self, model, tin, tout):
        p = price(model)
        usd = (tin * p["input"] + tout * p["output"]) / 1e6
        with self.lock:
            self.spent += usd
            with open(self.path, "a") as f:
                f.write(json.dumps({"at": now(), "model": model, "in": tin, "out": tout, "usd": round(usd, 6)}) + "\n")

    def check(self):
        if self.spent >= self.max_usd:
            raise BudgetExceeded(f"budget reached: ${self.spent:.2f} of ${self.max_usd:.2f}")


class BudgetExceeded(RuntimeError):
    pass


def run_parallel(jobs, workers, label):
    """jobs: list of zero-arg callables. Stops cleanly on BudgetExceeded."""
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(j) for j in jobs]
        try:
            for f in as_completed(futs):
                f.result()
                done += 1
                if done % 50 == 0 or done == len(jobs):
                    print(f"  {label}: {done}/{len(jobs)}", flush=True)
        except BudgetExceeded as e:
            for f in futs:
                f.cancel()
            print(f"STOPPED: {e}. Re-run the same command with a higher --max-usd to resume.", flush=True)
            raise


def git_head():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def manifest(outdir, cfg, providers, data_files):
    m = {"started_utc": now(), "git_head": git_head(), "python": sys.version.split()[0], "platform": platform.platform(),
         "config": cfg, "data_sha256": {f: sha256_file(f) for f in data_files},
         "available_models": {fam: p.list_models() for fam, p in providers.items()}}
    import importlib.metadata as md
    m["packages"] = {k: _version(md, k) for k in ("anthropic", "openai")}
    json.dump(m, open(os.path.join(outdir, "manifest.json"), "w"), indent=2)
    return m


def _version(md, pkg):
    try:
        return md.version(pkg)
    except Exception:
        return None
