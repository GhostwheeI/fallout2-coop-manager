# Gemini / Antigravity review and resolutions

Reviewed on 2026-10-26 through the installed Antigravity CLI (`agy`), in read-only
plan mode. Inputs included the recommendation, complete implementation spec and
actual Go TLS fixture. A second review examined the changed spec and source.
This is independent design feedback, not a certification or penetration test.

The follow-up verdict was **conditionally sound at the investigation/design
stage**, with the initial material findings resolved and remaining implementation
gates explicit. Its additional concrete issues were corrected as listed below.

| Finding | Resolution | Evidence / remaining boundary |
|---|---|---|
| A trusted CA certificate is weaker than an exact host leaf pin | Go fixture now uses a non-CA leaf, normal name/chain verification, plus exact DER equality in `VerifyConnection`; spec requires the same | Non-CA success test and substituted-host rejection pass |
| Handshakes and authorized streams shared one slot pool | Separate bounded pools, with the pending slot released after authentication | Pending-pool saturation test preserves an existing authenticated stream |
| Closing both sockets on first EOF can lose a response | Propagate half-close and allow bounded reverse-direction drain | Delayed-response-after-EOF test passes |
| Engine startup check ignored its possible second listener | Spec waits for game readiness, checks every PID-owned endpoint, permits only known loopback ports, and rechecks while hosting | Actual rebuilt engine/listener verifier still unimplemented and untested |
| IP echo can return a different address family from the listener | Spec requires family-specific dialing and validates the selected IPv6 address | Real IPv4/IPv6 home-network validation still required |
| Acknowledgement wording could imply the wrong byte count | Spec defines the exact eight-byte sequence; Go fixture sends and consumes it before game forwarding | Success path now includes that acknowledgement |
| One invitation could consume multiple concurrent streams | Reserve one stream per guest ID atomically; refuse duplicates without disconnecting the original | Concurrent-reuse test passes |
| Token checks short-circuited for unknown IDs; unknown revocation could panic | Always compare a stored/dummy token, then combine validity; unknown revoke becomes a no-op | Wrong/unknown credential and unknown-revoke tests pass |

The initial review also flagged a truncated comparison excerpt. The supplied
review prompt had been shortened; the actual comparison file was complete. The
compiler concern was checked directly: `go version go1.27.3 windows/amd64`, also
listed in the official release history. Neither was treated as an unfounded code
defect.

Final local evidence: **26 Python tests, 16 Go tests and 16 unchanged manager tests
pass**. Go vet passes; govulncheck reports no known vulnerabilities for the pinned
test dependency graph at scan time. The follow-up's acknowledgement, reuse and
revocation corrections were validated locally after that review; they have not
undergone a further external review or a public-network test.

The Python TLS fixture retains its simpler private trust-anchor/relay design and
temporary PEM loading; it is comparative research, not the proposed shipping
implementation. The Go fixture demonstrates the recommended boundaries but is
still test code, not a complete manager integration.

No candidate has earned release approval. Outstanding gates include the actual
patched engine build, production helper/GUI lifecycle, clean Windows packages,
two-PC/WAN and global IPv6, firewall/router cleanup, and one-hour game validation.
See [RESULTS.md](RESULTS.md) and [IMPLEMENTATION-SPEC.md](IMPLEMENTATION-SPEC.md).

Raw CLI transcripts stay in locally ignored `results/`; no credentials, private
invites, machine logs or downloaded binaries are published with this summary.
