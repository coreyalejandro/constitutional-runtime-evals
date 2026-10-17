import hashlib, json, os

import yaml


def test_archive_unchanged():
    m = json.load(open("archive/2026-04-tlc/ARCHIVE_MANIFEST.json"))
    assert m["source_commit"].startswith("75e7c66")
    for rel, h in m["files"].items():
        assert hashlib.sha256(open(os.path.join("archive/2026-04-tlc", rel), "rb").read()).hexdigest() == h, rel


def test_ci_workflow_is_valid_yaml():
    wf = yaml.safe_load(open(".github/workflows/ci.yml"))
    steps = wf["jobs"]["reproduce"]["steps"]
    assert any("make reproduce" in s.get("run", "") for s in steps)
    assert wf[True] if True in wf else wf["on"]  # 'on' parses as True in YAML 1.1
