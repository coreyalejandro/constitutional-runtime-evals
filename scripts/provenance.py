"""Provenance manifest: commit, environment, and SHA-256 of every data, archive and result file."""
import glob, hashlib, json, platform, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path


def git(*a):
    try:
        return subprocess.check_output(["git", *a], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


pats = ["data/*", "archive/**/*", "results/*.json", "results/*.md", "results/**/*.json", "results/**/*.jsonl", "results/**/*.md",
        "PREREGISTRATION.md", "requirements.txt", "config/*"]
files = sorted({f for p in pats for f in glob.glob(p, recursive=True)
                if Path(f).is_file() and not f.endswith(("PROVENANCE.json", "junit.xml")) and "/smoke/" not in f})
print(json.dumps({
    "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "git_commit": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain")),
    "python": sys.version.split()[0], "platform": platform.platform(),
    "seeds": {"permutation_tests": 0, "bootstrap": 0},
    "files": {f: hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in files},
}, indent=2))
