# SPARE host diagnostics

Run on Linux with Python 3 and Clang:

```sh
python3 tests/spare_ci/run.py --cc clang --sanitize /path/to/result
```

The queue harness exercises the saved SPARE classifier and dispatcher with a host FIFO and synthetic packets. It checks accepted and rejected ownership, release counts and FIFO order. The HTTPS harness exercises the original SPARE task and its archived response guard with synthetic calls for success, HTTP 503, header failure, partial body, allocation failure and open failure. PASS includes observing the original false successes and verifying that the guard rejects them.

The baseline manifest records SHA256 for saved SPARE inputs and separate archived A/B outputs. The fork parent supplies Git history for the CI branch. The firmware extracts were checked against the local SPARE source independently. Jobs compile host C fixtures. ESP-IDF builds, live TLS, pbuf/netif lifecycle and hardware qualification require separate evidence.

GitHub requires the workflow on the default branch to make its first manual dispatch available. Open or reopen a draft PR from diagnostic/spare-ci-20261119 into diagnostic/nettest-response-guard-20261118 to trigger the isolated smoke test. The job checks out the same-repository PR head commit. Updating the PR does not trigger the smoke test. The Linux command above exercises the same entry point. See [GitHub manual dispatch requirements](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).
