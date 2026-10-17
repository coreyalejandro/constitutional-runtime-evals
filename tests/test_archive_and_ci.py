import hashlib, json, os

import yaml


def test_archive_unchanged():
    m = json.load(open("archive/2026-04-tlc/ARCHIVE_MANIFEST.json"))
    assert m["source_commit"].startswith("75e7c66")
    for rel, h in m["files"].items():
        assert "__pycache__" not in rel
        assert hashlib.sha256(open(os.path.join("archive/2026-04-tlc", rel), "rb").read()).hexdigest() == h, rel


def test_ci_workflow_is_valid_yaml():
    wf = yaml.safe_load(open(".github/workflows/ci.yml"))
    steps = wf["jobs"]["reproduce"]["steps"]
    assert any("make reproduce" in s.get("run", "") for s in steps)
    assert wf[True] if True in wf else wf["on"]  # 'on' parses as True in YAML 1.1


def test_archive_has_no_untracked_files():
    m = json.load(open("archive/2026-04-tlc/ARCHIVE_MANIFEST.json"))
    on_disk = {os.path.relpath(os.path.join(d, f), "archive/2026-04-tlc") for d, _, fs in os.walk("archive/2026-04-tlc")
               for f in fs if "__pycache__" not in d} - {"ARCHIVE_MANIFEST.json"}
    assert on_disk == set(m["files"])
