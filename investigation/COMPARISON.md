# Account-free direct connections: feasibility decision

**Status: conditional architectural recommendation, not release approval.**
Investigation branch only. The released manager, game folders, binaries, router,
firewall, routes and Windows services were not modified.

## Recommendation

Prefer a **bundled, game-only TLS 1.3 connector**, implemented as a small Go helper
launched by the manager. A copyable invitation pins a unique host certificate and
contains a random, individual guest credential. The helper forwards one fixed
local game endpoint after authentication. No account, shared server, subscription,
VPN adapter or routing of other applications is needed.

The Python and Go prototypes both demonstrate this architecture. Prefer Go for
the eventual helper because its current standard-library TLS avoids adding the
Python certificate-generation dependency and avoids this laptop's old OpenSSL
3.0.16 TLS runtime. This is an implementation recommendation, not a claim that
the short prototype is a hardened public server.

**Neither candidate passes every production gate yet.** Both need a rebuilt,
validated engine with private listeners and real two-computer/WAN validation.
The official Windows WireGuard service additionally remains uninstalled/untested.

## Comparison

| Dimension | Application TLS connector | Official Windows WireGuard service | WireGuard userspace alternative |
|---|---|---|---|
| Player accounts / project infrastructure | None | None | None |
| Traffic | One authenticated TCP byte stream | IP tunnel over UDP | IP tunnel over UDP, inside private netstack |
| Guest setup target | Paste invite, Connect, Play | Install service/driver, then managed pairing | Paste invite, Connect, Play |
| Administrator | Only optional host firewall setup | Service/driver setup | Only optional host firewall setup |
| Other laptop services exposed by design | No; backend destination fixed | Must be isolated with interface firewall policy | No OS adapter or host routing; only explicit virtual listeners |
| Host router requirement | Reachable TCP endpoint | Reachable UDP endpoint | Reachable UDP endpoint |
| Restrictive UDP networks | Can use TCP where permitted | WireGuard has no native TCP mode | Same restriction |
| Additional stack | Go standard library | Windows service and kernel driver | WireGuard + gVisor + Go modules |
| Locally executed | Python and Go prototypes | Documentation/source assessment only | Official userspace library, loopback UDP adapter |
| Current recommendation | First choice | Do not choose as default | Credible second choice if TLS WAN tests disappoint |

The userspace WireGuard alternative is deliberately distinguished from the
official Windows service. Its successful tests do not validate driver install,
adapter firewall isolation or uninstall behavior. Neither tunnel traverses an
unreachable NAT by itself. No relay or public rendezvous is silently introduced.

## Evidence

See [RESULTS.md](RESULTS.md) for measured results and unrun tests. The local runs
passed **26 Python tests and 16 Go tests**. The unchanged manager's 16 tests also
passed. All prototype socket listeners and destinations were loopback-only.

- Python TLS: 1 MiB TCP payload, TLS 1.3, certificate validation, unknown/wrong
  credentials, expiration, active and individual revocation, host impersonation,
  protocol downgrade, malformed invitations, IPv6 loopback, cleanup and sampled
  wire confidentiality checks.
- Go TLS: both local TCP bridges, wrong/unknown credentials, expired/revoked
  guests, host impersonation, active revocation, TLS 1.3, exact non-CA host leaf,
  delayed-response drain after half-close, separate handshake/stream limits,
  success acknowledgement and refusal of simultaneous invitation reuse.
- WireGuard userspace: full local TCP bridge path, encrypted UDP samples,
  unknown and revoked keys, inaccessible unconfigured virtual ports, external
  endpoint refusal and UDP listener cleanup.
- Router policy: consent, private-backend prerequisite, finite lease, mapping
  ownership and cleanup. **A fake adapter was used; no real router was called.**

The first PSK experiment was rejected: Python's callback did not conveniently
attribute authenticated peers to application streams. A plaintext identity claim
would have allowed incorrect revocation attribution. Certificate-pinned TLS plus
credentials inside that verified encrypted channel avoids this ambiguity.

## Engine isolation is a common prerequisite

The latest published engine remains gusmarcum v1.4.3. Both game and admin sockets
bind `INADDR_ANY` in `src/server_net.cc`; the manager disables admin, but a TLS
wrapper alone cannot make the raw game socket private.

`prototypes/engine-loopback.patch` changes exactly those two bindings to
`INADDR_LOOPBACK`. The patch applies cleanly to upstream commit
`c2a7a7c5c69307d6845bd335e58085411d8ded0c`. The original checkout is unchanged.
The Windows socket-model test confirms that a loopback socket accepts local
connections and rejects connections addressed to the laptop's non-loopback IPs.

**This is not a rebuilt-engine test.** No C++ toolchain is present, so compiling
that engine, testing its actual listeners, and rerunning game regressions remain
mandatory before implementation can be released. Do not substitute firewall
assumptions or a Python socket model for this gate.

## Distribution, maintenance and costs

- Go standard-library helper: Go's BSD-style license and required notices; no
  runtime dependency on an installed Go toolchain. Pin a supported compiler and
  rerun vulnerability checks at release time.
- Python prototype: CPython/PSF, OpenSSL license notices and cryptography's
  Apache-2.0/BSD licensing must be inventoried if distributed. Prototype files
  are research code; dependencies are not added to the manager's release.
- wireguard-windows source is MIT; wireguard-go is MIT; gVisor is Apache-2.0;
  the WireGuardNT source COPYING is GPLv2. Preserve separate component notices
  and assess the exact chosen binaries/source obligations before bundling.
  Do not label the driver stack uniformly MIT.
- Existing engine remains under its Sustainable Use License. A modified build
  needs an explicit modification notice, exact source/patch, hashes and its
  existing notices; the manager's MIT license does not replace engine terms.
  Redistribution must remain free of charge and non-commercial under those terms.
- No project-operated service or recurring infrastructure bill. A public IPv4
  from an ISP can cost an individual host money; never describe that as free.
- Authenticode signing is not assumed available for free. Unsigned executable
  warnings remain a usability limitation; never advise disabling protection.

## Setup, compatibility and update burden

The proposed TLS package needs no Python/Go installation on either player's PC:
the manager runtime and helper are bundled. The host prepares a world, chooses an
approved home interface, and authorizes a narrow firewall rule if required. If
inbound IPv4 is not already reachable, the host explicitly requests a finite router
mapping or follows manual forwarding instructions for TCP 19432. The guest pastes
the private invitation and connects. Both still need their own Fallout 2 files.

For the official Windows WireGuard embedding path, the developer must build and
bundle `tunnel.dll`, select the matching `wireguard.dll`, install the tunnel service
with its service SID, restrict adapter firewall access to the game, provision
individual keys, and remove service/adapter/rules on stop. Both PCs need elevation
for that path. An invitation alone does not implement this lifecycle. The tested
userspace variant avoids the service/adapter but adds gVisor and bridge maintenance.

Go's documented platform baseline and WireGuard's current Windows installer both
include Windows 10/11. The manager's initial proposed target is **x64 Windows
10/11**, with clean-image support still unverified. This is compatibility intent,
not a claim that an unpatched Windows 10 installation has current OS security support.
No ARM64/32-bit complete-game package is validated here.

Go 1.27.3 is the exact tested compiler. Its current release includes X.509 security
fixes; rebuild the TLS helper for applicable future advisories and distribute it
through versioned manager updates. WireGuard's Windows source has September 2026
maintenance commits and lists installer 1.1.1; the userspace probe pins its October
2026 WireGuard commit. These are evidence of activity, not a support contract.
Embedding requires us to track/update the selected DLLs ourselves; a third-party
manager cannot assume the standalone WireGuard app will update its private copies.

Packaging evidence is limited to stripped test executables: approximately 6.2 MiB
TLS and 6.8 MiB userspace WireGuard. No complete embedded Windows service bundle
was built or measured. Final shipping sizes, signed-binary handling and driver
redistribution obligations remain explicit packaging gates.

Ranking is conditional on passing all security/release gates: TLS first for setup
effort, fixed game-only exposure and fewer dependencies; userspace WireGuard second;
the Windows service third because of elevated lifecycle and adapter restrictions.
There is no defensible performance winner from these different loopback workloads.

## Limits and fallback order

1. Direct LAN connection using the same authenticated connector.
2. Reachable home endpoint, with an explicitly approved finite router mapping
   when supported; otherwise manual host-only router instructions.
3. Direct global IPv6 when both players have working IPv6 and the host authorizes
   the narrow inbound firewall rule.
4. If blocked, let the reachable player host; explain double NAT/CGNAT and ISP options.
5. Only after explicit user selection, show the existing external-VPN guide.
   Never require an account or switch to provider infrastructure automatically.

The public-IP lookup is optional and is not an outside-in reachability test.
It must be possible to enter the address manually. A short numeric join code
that looks up a session centrally conflicts with the direct-only requirement;
the proposed invitation is self-contained and copied privately.

## Primary sources checked

- [Python 3.13 TLS](https://docs.python.org/3.13/library/ssl.html)
- [Go crypto/tls](https://pkg.go.dev/crypto/tls), [Go license](https://go.dev/LICENSE)
- [Go Windows baseline](https://go.dev/wiki/MinimumRequirements),
  [Go release/support history](https://go.dev/doc/devel/release)
- [OpenSSL support policy](https://openssl-library.org/policies/releasestrat/index.html)
  lists OpenSSL 3.0 as unsupported; this laptop reports 3.0.16.
- [WireGuard embedding](https://www.wireguard.com/embedding/),
  [Windows embedding service](https://git.zx2c4.com/wireguard-windows/about/embeddable-dll-service/README.md)
- [WireGuard limitations](https://www.wireguard.com/known-limitations/)
- [WireGuard supported Windows versions](https://www.wireguard.com/install/),
  [Windows maintenance log](https://git.zx2c4.com/wireguard-windows/log/)
- [wireguard-go netstack example](https://github.com/WireGuard/wireguard-go/tree/master/tun/netstack)
- [Windows WireGuard license](https://git.zx2c4.com/wireguard-windows/plain/COPYING),
  [WireGuardNT license](https://git.zx2c4.com/wireguard-nt/plain/COPYING)
- [cryptography license choice](https://raw.githubusercontent.com/pyca/cryptography/main/LICENSE),
  [gVisor license](https://raw.githubusercontent.com/google/gvisor/master/LICENSE)
- [Windows firewall rule scopes](https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule)
- [Existing engine and limitations](https://github.com/gusmarcum/fallout2-coop/tree/v1.4.3)
