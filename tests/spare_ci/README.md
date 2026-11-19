# SPARE host diagnostics

Run on Linux with Python 3 and Clang:

```sh
python3 tests/spare_ci/run.py --cc clang --sanitize /path/to/result
```

The queue harness exercises the saved SPARE classifier and dispatcher with a host FIFO and synthetic packets. It checks accepted and rejected ownership, release counts and FIFO order. The HTTPS harness exercises the original SPARE task and its archived response guard with synthetic calls for success, HTTP 503, header failure, partial body, allocation failure and open failure. PASS includes observing the original false successes and verifying that the guard rejects them.

The baseline manifest records SHA256 for saved SPARE inputs and separate archived A/B outputs. The fork parent supplies Git history for the CI branch. The firmware extracts were checked against the local SPARE source independently. Jobs compile host C fixtures. ESP-IDF builds, live TLS, pbuf/netif lifecycle and hardware qualification require separate evidence.

GitHub requires the workflow on the default branch to make its first manual dispatch available. Open or reopen a draft PR from diagnostic/spare-ci-20261119 into diagnostic/nettest-response-guard-20261118 to trigger the isolated smoke test. The job checks out the same-repository PR head commit. Updating the PR does not trigger the smoke test. The Linux command above exercises the same entry point. See [GitHub manual dispatch requirements](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

## Additional isolated pbuf ownership contract

The `pbuf-lifecycle.c` fixture is a **synthetic host-only model**, not
production ESP-IDF/lwIP or the SPARE WireGuard sender. It checks that:

- Exclusive reference count 1 permits mutation/send.
- An extra reference rejects an in-place send, while a privately copied buffer
  can be sent without modifying the shared source.
- Allocation failure rejects the copy, an inactive netif rejects send, and
  a released buffer cannot be reused.

This validates the intended ownership **contract**, not the source of the
observed panic at `ip4.c:929`. It does not reproduce the device's 13-frame
backtrace, prove queue/netif lifetimes in production, or qualify OTA.
The CI report explicitly distinguishes this mock PASS from production
pbuf/netif lifecycle, which remains NOT PROVEN.

## WG12 queue overlap hypothesis (archived October source)

The `wg12-interleaving.c` test models the ownership transition in an
**archived October** `ml_wg_mgr.c`: `wg12_enqueue` retains the original
`pbuf` and `wg12_flush_cb` submits it to `udp_sendto`. It exercises
(1) normal release-before-flush, (2) flush-before-caller-release, and
(3) an independent extra reference. Scenarios (2) and (3) deliberately
detect a nonexclusive buffer (`ref == 2`), without triggering a host
abort. Passing means the model identifies the hazardous ordering; it
does **not** mean that the deployed `0.1.40-tlsca1` has this race or
that the historical `ip4.c:929` assertion is caused by it.

The installed November 17 source and its exact 13-frame trace must be
compared separately before modifying production code. The earlier
`source_audit.py` examines the fork's pinned public MicroLink submodule,
which does not have the same WG12 queue implementation.

## ERR_MEM retry reference model

`wg12-retry-model.c` models the historical WG12 behavior when a queued
pbuf is sent and `udp_sendto` returns `ERR_MEM`. It checks both a
retry retaining exactly one queue reference, and a hypothetical failure
path where another component still retains a pbuf reference. The second
scenario deliberately detects the violation of the exclusive-reference
contract; it does not imply that ESP-IDF's actual driver retains the
buffer on `ERR_MEM`. A separate-copy case models one possible
ownership isolation concept but is **not** a production fix.

The exact deployed `0.1.40-tlsca1` source has not been retrieved
from the user's local `D:\\ChatGPT` archive into this public CI. Do not
promote these historical-source models to a root-cause finding until
provenance and the deployed path are verified. No device secret, NVS
state or private identity should be uploaded to the public repository.

## Exact local source verification (no upload)

Given a trusted local copy of November 17 SPARE `0.1.40-tlsca1`
`ml_wg_mgr.c` under `D:\\ChatGPT`, use
`python tests/spare_ci/verify_local_source.py PATH_TO_ML_WG_MGR_C`.
The helper reads and hashes the source only; it does not publish source,
NVS, tokens, identity or firmware. Exit code 0 means the local file
matches the archived manifest SHA256, 2 means mismatch, 3 means blocked
or inaccessible. Even a SHA match does not prove a flash readback or
the root cause of the PANIC.

The public CI workflow uses the public MicroLink submodule only as an
expected-MISMATCH negative control. Do NOT upload local firmware
sources or private secrets into this public repository.

## Uploaded exact-source verification (19 November 2026)

The operator provided the exact local `ml_wg_mgr.c` separately. A read-only
SHA256 comparison in the analysis chat matched the archived manifest
`686e44d1f0f305de8250563aa2ef5630144f4b714b1191d1a7736d7d3fc46ba8`
(124422 bytes). **This is an external source attestation, not a claim that
GitHub CI contains the source or has performed a flash readback.** No uploaded
source or private firmware data was committed.

The attested file has `wg12_enqueue` retaining its input `pbuf`
(line 497); `wg12_flush_cb` sends the same queued pointer from the TCPIP
thread (line 543), with release at line 568, and re-enqueues on
`ERR_MEM` (lines 550–562). The borrowed-TX entry points can enqueue
from backlog (line 865) or after a driver `ERR_MEM` (line 871). The
synchronous rendezvous wrapper lives at lines 307–347. These source facts
support a possible shared-reference interleaving; they **do not** prove that
the deployed system reached it during its 18 November PANIC.

The `wg12-copy-per-attempt.c` host test explores an alternative design:
the queue owns a byte copy, each transmission uses its own independently
owned pbuf, and retries never reuse a potentially shared outgoing pbuf.
This is an illustrative synthetic model, NOT an applied firmware patch.
It deliberately reports no improvement in hardware throughput or proof
of panic elimination. Further testing with exact lwIP/Wi-Fi interfaces
and error-contract evidence is needed before production modification.

## 2026-11-19: exact-source lwIP TX ownership assessment

Only the exact **uploaded** SPARE manager source (SHA256
`686e44d1f0f305de8250563aa2ef5630144f4b714b1191d1a7736d7d3fc46ba8`)
has been source-attested; it is **not** committed here.
Its WG12 queue has capacity 8, 3000 us timer period, 50000 us TTL,
and 2 maximum attempts. `wg12_enqueue` calls `pbuf_ref`;
`wg12_flush_cb` sends the same pointer through a blocking TCPIP
rendezvous, and frees its queue reference afterward.
`wgopt1_udp_pbuf_output_cb` can enqueue on backlog or after
`ERR_MEM` and the original WireGuard caller retains its original
reference until it finishes the callback. The observed
`ip4_output_if_opt_src` assert is consistent with a flush before
the caller drops the original reference, but that ordering has
**not** been observed in device telemetry.

Design decision for future controlled test only: do NOT copy every
WireGuard packet. Evaluate queue-only byte ownership and independent
per-attempt transmission buffers. At a working assumption of 1312 bytes
payload and queue depth 8, queue-owned byte storage adds
8*1312 = 10496 bytes (10.25 KiB), before allocation metadata,
alignment and protocol headroom. A +28-byte UDP/IPv4 header allowance
would yield 10720 bytes (~10.47 KiB); actual pbuf/heap overhead,
fragmentation, cap and internal-versus-SPIRAM placement remain
**NOT PROVEN**. If all 140 packets/s were copied this would add
183680 bytes/s of payload copying, but queue-only traffic is unknown.
Do not interpret these estimates as RAM measurements, performance
measurements, or a guaranteed fix.

Unresolved evidence before production patch:
1. Obtain and hash the exact installed SDK 6.1 lwIP `udp.c`,
   `ip4.c`, `pbuf.c` and relevant output path.
2. Verify pbuf header pointer/length state after every `ERR_MEM`
   return path; a retry can be unsafe even with reference count 1.
3. Prove exact caller's original-reference release ordering and
   downstream Wi-Fi TX reference lifecycle.
4. Run finite, deterministic actual-code tests before ANY OTA.
No devices, auth material, NVS, identity or installed firmware
are accessed by this CI branch.
