"""Verify a *local* SPARE source against an archived digest without publishing code.

Usage (Windows, with exact local file):
  python tests/spare_ci/verify_local_source.py "D:\\ChatGPT\\path\\ml_wg_mgr.c"
Returns 0 for archive-SHA match, 2 for mismatch, 3 for inaccessible file.
Does not copy, print, or upload the source. SHA match is not a flash readback.
"""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
EXPECTED = json.loads((ROOT / "baseline.json").read_text(encoding="utf-8"))[
    "microlink_wg_mgr_sha256"
]

def main():
    if len(sys.argv) != 2:
        print("Usage: verify_local_source.py PATH_TO_ML_WG_MGR_C", file=sys.stderr)
        return 3
    source = Path(sys.argv[1]).expanduser().resolve()
    if os.name == "nt":
        permitted = Path("D:/ChatGPT").resolve()
        if source != permitted and permitted not in source.parents:
            print("BLOCKED: source is outside permitted D:/ChatGPT", file=sys.stderr)
            return 3
    try:
        if not source.is_file() or source.is_symlink():
            raise OSError("source is not a regular file")
        digest = hashlib.file_digest(source.open("rb"), "sha256").hexdigest()
    except OSError:
        print("NOT PROVEN: source missing or inaccessible", file=sys.stderr)
        return 3
    status = "MATCH" if digest == EXPECTED else "MISMATCH"
    print(json.dumps({
        "scope": "local source SHA256 against archived 2026-11-17 SPARE manifest",
        "result": status,
        "actual_sha256": digest,
        "expected_sha256": EXPECTED,
        "deployed_flash_readback": "NOT PROVEN",
        "production_panic_root_cause": "NOT PROVEN",
        "source_content_uploaded": False,
    }, indent=2))
    return 0 if status == "MATCH" else 2

if __name__ == "__main__":
    raise SystemExit(main())
