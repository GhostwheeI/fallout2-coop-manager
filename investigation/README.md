# Direct-connection feasibility investigation

- [Comparison and recommendation](COMPARISON.md)
- [Actual results and missing test environments](RESULTS.md)
- [Follow-on implementation specification](IMPLEMENTATION-SPEC.md)
- [Gemini review and resolutions](REVIEW.md)

This directory contains isolated prototypes, not features of the released manager.
They refuse external transport endpoints and must not be used to host public games.
No game assets, runtime downloads, keys or invitations are included in Git.

## Reproduce local probes

Use Python 3.13 (tested) and install the pinned research dependency in an isolated
environment. The Python certificate prototype is not a recommendation to ship an
old OpenSSL runtime. From the repository root:

```powershell
python -m venv investigation/tools/venv
investigation/tools/venv/Scripts/python.exe -m pip install cryptography==50.0.2
investigation/tools/venv/Scripts/python.exe -m unittest discover -s investigation/prototypes -p 'test_*.py' -v
```

Or use an already isolated interpreter with that dependency installed:

```powershell
python -m unittest discover -s investigation/prototypes -p 'test_*.py' -v
```

With a supported Go toolchain, from `investigation/prototypes`:

```powershell
go test ./... -v -count=1 -timeout 90s
go run golang.org/x/vuln/cmd/govulncheck@v1.9.0 -test ./...
```

Go module versions and integrity sums are pinned beside the probes. The tests use
official WireGuard userspace/netstack APIs; their custom UDP adapter only restricts
transport to loopback and samples ciphertext, not cryptographic operations.

For the source patch check, provide an upstream v1.4.3 checkout:

```powershell
python investigation/prototypes/make_engine_patch.py PATH_TO_ENGINE/src/server_net.cc investigation/prototypes/engine-loopback.patch
git -C PATH_TO_ENGINE apply --check ABSOLUTE_PATH_TO_PATCH
```

This only generates/checks a patch. A full engine build and separate-PC listener
verification are still required. Router tests use an in-memory fake router only.
The Python source-patch test looks for the optional engine checkout at
`review/gusmarcum`; without it, that test reports a skip. The recorded 26/26 local
run includes upstream source at commit `c2a7a7c5c69307d6845bd335e58085411d8ded0c`.

Local raw output is kept under ignored `results/`; measured summaries are in
RESULTS.md. Tools and private fixtures are ignored. Do not upload diagnostic files
or crash dumps containing real invitations, credentials or personal addresses.
