"""Read-only inventory of the fork-pinned MicroLink sender (NOT live SPARE)."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

repo = Path(__file__).resolve().parents[2]
sub = repo / "external" / "microlink"
output = Path(sys.argv[1])
expected_gitlink = "17a8c9c0b9f6d7871fd1430f800383c87b99caa2"
source = sub / "components/microlink/src/ml_wg_mgr.c"
baseline = json.loads((Path(__file__).resolve().parent / "baseline.json").read_text(encoding="utf-8"))
report = {
    "deployed_spare": {
        "firmware": baseline["version"],
        "build": baseline["build"],
        "expected_manager_sha256": baseline["microlink_wg_mgr_sha256"],
        "expected_ip4_sha256": baseline["ip4_source_sha256"],
    },
    "scope": "fork-pinned public MicroLink source, not attested SPARE 0.1.40-tlsca1",
    "installed_spare_panic_root_cause": "NOT PROVEN",
    "installed_spare_pbuf_lifecycle": "NOT PROVEN",
    "checks": {}
}
try:
    actual = subprocess.check_output(["git", "-C", str(sub), "rev-parse", "HEAD"], text=True).strip()
    report["submodule_commit"] = actual
    report["checks"]["expected public submodule gitlink"] = "PASS" if actual == expected_gitlink else "FAIL"
    data = source.read_bytes()
    report["source_sha256"] = hashlib.sha256(data).hexdigest()
    report["deployed_spare"]["source_match"] = (
        "MATCH" if report["source_sha256"] == baseline["microlink_wg_mgr_sha256"]
        else "MISMATCH"
    )
    report["deployed_spare"]["comparison_status"] = (
        "PASS" if report["deployed_spare"]["source_match"] == "MATCH"
        else "NOT PROVEN"
    )
    text = data.decode("utf-8")
    start = text.index("static err_t wg_udp_output_cb(")
    end = text.index("/* tailscale \"send both\"", start)
    send = text[start:end]
    predicates = {
        "custom pbuf allocation": "pbuf_alloced_custom(" in send,
        "lwIP udp_sendto": "udp_sendto(" in send,
        "sender pbuf_free": "pbuf_free(p)" in send,
        "SPIRAM payload": "MALLOC_CAP_SPIRAM" in send,
        "PBUF_REF payload": bool(re.search(r"pbuf_alloced_custom\([^;]+PBUF_REF", send, re.S)),
        "free occurs after send": send.find("udp_sendto(") < send.find("pbuf_free(p)"),
    }
    report["checks"].update({name: "PASS" if present else "FAIL" for name, present in predicates.items()})
    report["notes"] = [
        "Source guards assert presence/order only, not safety across asynchronous driver lifetimes.",
        "Public gitlink and archived deployed source SHA256 are independently compared; a mismatch must not fail this source-only inventory but blocks deployed-source claims.",
        "Exact installed SPARE source and wg12_flush_cb are not contained in this pinned submodule check.",
        "No PANIC reproduction or ESP-IDF SDK matrix is claimed."
    ]
except (OSError, ValueError, subprocess.CalledProcessError) as exc:
    report["checks"]["read public submodule source"] = "FAIL"
    report["error"] = type(exc).__name__
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
sys.exit(1 if "FAIL" in report["checks"].values() else 0)
