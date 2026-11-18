"""Build and run the archived SPARE host extracts with synthetic test doubles."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def run(command):
    subprocess.run(command, check=True, timeout=90)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cc", default="clang")
    parser.add_argument("--cc-arg", action="append", default=[])
    parser.add_argument("--sanitize", action="store_true")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if os.name == "nt":
        import sys
        sys.path.insert(0, r"D:\ChatGPT\Work\Tools")
        from storage_guard import install_write_guard
        install_write_guard()
    root = Path(__file__).resolve().parent
    args.output.mkdir(parents=True, exist_ok=True)
    compiler = [args.cc, *args.cc_arg]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    version = subprocess.check_output([*compiler, "--version"], text=True, timeout=10).splitlines()[0]
    manifest = json.loads((root / "baseline.json").read_text(encoding="utf-8"))
    checks = {
        "fixture SHA256": "FAIL",
        "queue ownership and FIFO (240 epochs)": "NOT PROVEN",
        "HTTPS response and cleanup (six mocked cases per variant)": "NOT PROVEN",
        "ASan and UBSan": "NOT PROVEN",
        "full Host Lab 3 / pbuf / netif lifecycle": "NOT PROVEN",
        "ESP-IDF 5.5.3/y, 6.1/y and 6.1/n builds": "NOT PROVEN",
        "PANIC predicate, hardware behavior and throughput": "NOT PROVEN",
    }
    flags = ["-std=c11", "-g", "-O1", "-UNDEBUG", "-pthread"]
    if args.sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
    failed = False
    try:
        for name, expected in manifest["fixtures_sha256"].items():
            actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f"Fixture digest mismatch for {name}")
        checks["fixture SHA256"] = "PASS"
        for check, cases in (
            ("queue ownership and FIFO (240 epochs)", [("queue", "queue.c", [])]),
            ("HTTPS response and cleanup (six mocked cases per variant)", [
                ("https-before", "https-before.c", []),
                ("https-after", "https-after.c", ["-DFIXED"]),
            ]),
        ):
            checks[check] = "FAIL"
            if args.sanitize:
                checks["ASan and UBSan"] = "FAIL"
            for executable, source, defines in cases:
                binary = (args.output / (executable + (".exe" if os.name == "nt" else ""))).resolve()
                run([*compiler, *flags, *defines, str(root / source), "-o", str(binary)])
                run([str(binary)])
            checks[check] = "PASS"
        if args.sanitize:
            checks["ASan and UBSan"] = "PASS"
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Host lab failed ({type(error).__name__})", flush=True)
        failed = True
    report = {"commit": revision, "compiler": version, "flags": flags,
              "baseline": manifest, "checks": checks}
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = ["# SPARE host diagnostics", "", f"Commit `{revision}`", "", f"Compiler `{version}`",
             "", "| Check | Result |", "|---|---|"]
    lines.extend(f"| {check} | {status} |" for check, status in checks.items())
    (args.output / "result.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
