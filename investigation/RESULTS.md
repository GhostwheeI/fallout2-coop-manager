# Test evidence and limits

## Environment

One existing Windows 11 laptop; not a clean OS image. Python 3.13 with OpenSSL
3.0.16, isolated cryptography 50.0.2, portable Go 1.27.3. No virtual network
adapter, service, route, firewall or router was installed/configured. This was
not a two-PC game test. Echo services model the raw TCP game stream.

## Recorded local results

| Suite | Result | What the result establishes |
|---|---|---|
| Python pinned-TLS prototype | 16/16 | Local stream integrity, invitation checks, rejection/revocation, TLS downgrade/impersonation refusal, IPv6 loopback, sampled ciphertext and listener cleanup |
| Fake router policy | 8/8 | Consent, finite lease, ownership, collision refusal and safe cleanup policy—not actual UPnP/PCP interoperability |
| Engine patch/socket model | 2/2 | Patch affects both listeners without modifying original; Winsock loopback isolation works—not an engine binary proof |
| Go standard-library TLS | 9/9 | Authenticated local proxy path, credentials/revocation, exact non-CA leaf pin, TLS 1.3, half-close drain, separate admission pools, success acknowledgement and concurrent invite reuse refusal |
| WireGuard userspace | 7/7 | Local encrypted UDP path, fixed virtual service, key rejection/revocation, both TCP bridges and cleanup |
| Existing manager baseline | 16/16 | Existing manager tests remain passing; production code not changed |
| Go vulnerability scan | No vulnerabilities found | govulncheck v1.9.0 with test entrypoints, pinned modules and current database; not a security audit or future guarantee |
| Engine patch applicability | Passed | `git apply --check` against c2a7a7c5c69307d6845bd335e58085411d8ded0c |

Example loopback samples: Go TLS echoed 114,688 bytes through both TCP bridges
and TLS in about 4–7 ms; WireGuard echoed 72,000 bytes in about 7 ms. Workloads
and paths differ. **These are not comparative WAN benchmarks.** No conclusion
that either transport is faster follows from these samples.

Stripped standalone test executables measured about 6.2 MiB for Go TLS and
6.8 MiB for WireGuard. These include test harnesses and are not production bundle
size claims; the final packaged helper must be measured again.

Raw runs are retained locally under ignored `results/`; keys, invitations,
downloaded runtimes and binaries are excluded from version control. Source tests
and module versions/checksums are supplied for reproduction. The initial PSK
attempt failed success-path tests and was discarded, rather than counted as a
passing result.

Gemini/Antigravity reviewed the recommendation, complete spec and Go TLS source.
See [REVIEW.md](REVIEW.md) for findings, corrections and remaining release gates.
`go vet ./...` also passed. The Go race detector was not run (no C/race toolchain).

## External/production matrix—explicitly NOT RUN

| Required scenario | Status / reason |
|---|---|
| Rebuilt modified engine listener verification | Not run: no C++ toolchain; only source patch and socket model validated |
| Two physical computers on same LAN | Not run: only one laptop available |
| Different residential IPv4 networks | Not run: no second host/home network under test |
| Real global IPv6 | Not run: IPv6 loopback only is covered |
| Actual double NAT and CGNAT | Not run: no controlled router/ISP testbed |
| Windows Firewall denial/allow/cleanup | Not run: no real firewall changes authorized for this investigation |
| Actual UPnP/PCP router mapping, renewal and cleanup | Not run: fake policy adapter only |
| Official Windows WireGuard driver/service install/uninstall | Not run: would change system networking; userspace alternative tested instead |
| Clean Windows 10 and Windows 11 | Not run: current laptop is existing Windows 11, not disposable clean images |
| One-hour two-PC Fallout session with save/restart | Not run: requires rebuilt engine, second PC, users and a permitted network |
| Real network roaming/ISP change | Not run: no network change performed |
| Public-IP lookup | Not run: current work/VPN address is not the intended home endpoint |

These are release blockers, not failures silently replaced by loopback tests.
The architectural recommendation is provisional until the chosen approach passes
the missing applicable rows.

## Security gate disposition

| Gate | Local finding | Production disposition |
|---|---|---|
| Authenticated encryption | TLS 1.3 host verification + per-guest credentials; WireGuard keys | Locally demonstrated; production helper and WAN path still required |
| Raw game/admin remain private | Minimal patch + OS socket model only | **Not yet established for the actual engine binary** |
| Game-only access | Fixed proxy backend; unconfigured WireGuard virtual ports reject | Locally demonstrated; second-PC raw/admin/other-port attempts required |
| No universal secret | All host/session/guest material generated at runtime | Supported by prototype source; inspect packaged production build again |
| Safe failure | Local rejects, revoke/stop cleanup, bounded Go TLS admission | Incomplete until real firewall/router/crash/network-change tests pass |

No candidate is marked as passing all gates. The official Windows embedding path
has no executed service/driver evidence in this investigation.

## Remaining validation procedure

Run the packaged prerelease on disposable clean Windows 10 and 11 x64 images,
then on two physical PCs with licensed game files. Record exact OS/engine/helper
versions, package hashes, topology and observed sockets without recording invites.

1. Before public admission, inspect both engine listeners by PID and attempt raw
   game/admin access from the other PC. Only the encrypted endpoint may be reachable.
2. Repeat the full actual game path on LAN, separate reachable IPv4 home networks
   and global IPv6. Verify no adapter, route or unrelated port becomes accessible.
3. Reproduce double NAT, CGNAT, inbound denial, router mapping disabled and address
   family mismatch. Expect explicit unreachable/setup guidance, never a provider
   switch or success merely because a public-IP echo request worked.
4. Reject wrong, expired/revoked and substituted-host invitations before backend
   gameplay. During a good connection, revoke that guest and verify immediate
   disconnect and refused reconnect while a different authorized guest still works.
5. In an hour-long two-PC session, save at 20 minutes, disconnect/rejoin at 30,
   save and restart the host at 45, issue a fresh invite, and verify both players'
   state at 60. Record crashes, lost progress, reconnect behavior and stream errors.
6. Deny the firewall prompt, kill the GUI/helper/engine independently, change the
   approved interface, and restart. Expect closed admission, invalid old invites
   after restart, and cleanup/reconciliation of only owned rules. When automatic
   mapping is later introduced, repeat renewal failure, finite lease expiry, normal
   removal and externally replaced-mapping preservation on actual routers.

Acceptance requires every applicable row to pass, no exposed raw/admin listener,
and a new guest completing paste/connect/play without commands or file editing.
