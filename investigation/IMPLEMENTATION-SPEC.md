# Follow-on implementation specification: direct TLS connector

**Proposed after feasibility; not implemented in the released manager.**
Use the game-only TLS connector unless the remaining validation rejects it.
Do not install the WireGuard driver or create a project service as a fallback.

## 1. Boundaries and prerequisites

- Keep Python/Tk for the manager. Add one hidden Go helper executable using the
  supported Go standard library, initially Go 1.27.3, with TLS 1.3 only. The
  helper handles certificates, random credentials, sockets and public-IP lookup;
  do not use the current Python/OpenSSL 3.0.16 for public TLS.
- Build a separately identified engine from upstream v1.4.3 plus the supplied
  two-line loopback patch. Both raw listeners must bind only 127.0.0.1. Keep admin
  disabled. No protocol, gameplay or save format changes.
- Reproduce the engine build in Windows CI, publish source/patch and notices,
  pin new hashes, and rerun existing game regressions plus real listener checks.
  Keep the old public release untouched until the new release gates pass.
- Wait up to 30 seconds for the engine PID's game listener to become ready on
  127.0.0.1. Inspect every TCP/UDP listening/bound endpoint owned by that PID:
  allow only the configured loopback game port and, if upstream still creates it
  despite admin being disabled, the known loopback admin port. Never forward admin.
  Refuse unspecified addresses, non-loopback addresses and unexpected listeners.
  Recheck every second while hosting; any mismatch closes public admission and
  active tunnels immediately. Failure stops startup; never expose the stock raw
  listener. The patched binary, rather than polling alone, provides isolation.

## 2. Connection and invitation contract

- Introduce a provider-neutral manager adapter: `start_host`, `create_invite`,
  `join`, `status`, `revoke_guest`, `stop`. The first new provider is `tls-direct`;
  retain existing manual private-VPN joining under Advanced.
- Host helper connects only to the fixed local engine address/port supplied at
  startup. Guest helper listens only on an OS-selected 127.0.0.1 port and returns
  that endpoint for `F2_CLIENT_CONNECT`. Guests cannot request other destinations.
- Control the helper over inherited anonymous stdin/stdout pipes using bounded,
  versioned JSON messages. Never put credentials in process arguments, environment
  variables, ordinary settings, crash reports or diagnostic events. Reject unknown
  commands/versions and oversized messages; close sessions if the parent exits.
- Invitations use a self-contained `f2coop://v2/` base64url JSON envelope, maximum
  8 KiB, with exactly: version 2, kind `tls-direct`, literal public/LAN IP,
  encrypted endpoint port, host certificate DER, random 128-bit guest ID,
  random 256-bit guest secret, and expiry in UTC epoch seconds. No session lookup.
  Reject duplicate/unknown fields, invalid types, non-canonical key encodings,
  invalid ports and expired invitations before dialing. No DNS names, URL fetches,
  executable commands or guest-selected backend destinations. IPv6 is a bare
  literal in JSON and bracketed only when forming a socket address.
- Generate an in-memory P-256 self-signed server certificate per hosted session,
  valid for 24 hours: non-CA leaf, digital-signature usage only, server-auth EKU,
  SAN `f2coop-session`. Trust only that certificate as an explicit root and verify
  its name/validity with the normal Go verifier. Additionally require byte-for-byte
  equality of the presented leaf DER and invitation DER in `VerifyConnection`.
  Never set `InsecureSkipVerify`. Warn before certificate expiry and require a new
  hosted session/invitations after expiry; do not extend expired credentials.
  TLS authenticates before credentials/gameplay; disable tickets/resumption.
- After TLS, send a fixed-size guest credential frame and validate it in constant
  time before opening the engine connection. Give each invitation its own credential.
  Wire frame is exactly 16 bytes guest ID followed by 32 bytes secret. On success,
  connect the backend and send exactly eight total bytes: the six ASCII bytes
  `F2COOP` followed by version byte `0x02` and status byte `0x00` (hex:
  `46 32 43 4f 4f 50 02 00`), before forwarding game bytes. Rejects close without forwarding;
  return only a generic authentication failure to untrusted peers. The guest
  consumes this acknowledgement before admitting gameplay and showing Connected.
  Default expiry is ten minutes for new connections; connected guests remain
  authorized until disconnect, revoke or session stop. After expiry, reconnect
  requires a fresh invite. Revocation closes that guest's active streams and blocks
  reconnects. Keep credentials only in memory; restarting invalidates all invites.
  Permit at most one active/admitting stream per guest ID, reserved atomically
  under the guest-state lock before backend access. Reject concurrent reuse without
  disturbing the original stream; release the reservation on every error/disconnect.
  Always compare a stored or dummy 32-byte token before combining validity checks.
  Revoking an unknown/already revoked ID is an idempotent no-op.
- Invitation possession grants access. Explain private sharing and support immediate
  revoke/replace. This does not add ownership authentication to Fallout's player
  names: authorized friends remain trusted within the game.
  Host identity is anchored to the invitation, not a public identity directory:
  use an already trusted private sharing channel or compare the full SHA-256 host
  certificate fingerprint out of band. Replacing the entire invitation cannot be
  detected without that trust. First release accepts pasted text only; do not
  register a clickable OS URI handler or put secret invitations in browser history.
  Offer clipboard clearing, without promising to erase third-party clipboard history.

## 3. Public-user flow and diagnostics

- Main choices remain Host and Join. Host: prepare world, choose Home/approved
  network, run reachability checks, start securely, Copy invitation. Guest:
  prepare game, paste invitation, Connect and Play. No terminal/config-file steps.
- Start in loopback-only state. Public listening needs explicit host consent for
  the selected network interface/address; never silently run on a work network or
  change its Public/Private classification. Ask for elevation only for a narrowly
  described firewall change, not for the entire GUI.
- Prefer default encrypted TCP port 19432, separate from raw game port 9300.
  Permit user override if occupied. Bind only the chosen approved interface.
- Optional IP discovery uses a fixed HTTPS IP-echo endpoint, no account/cookies,
  bounded response/timeout and strictly parsed IP. Offer manual entry. Do not claim
  this proves reachability; the guest performs the real outside-in connection test.
  Choose `tcp4` or `tcp6` from the approved bound address. For IPv4, force the echo
  request to IPv4 on that interface; for IPv6 advertise the bound global unicast
  address, verifying any echo result agrees. Reject family mismatches, link-local
  and unspecified public endpoints. IPv6 needs an inbound firewall/pinhole decision,
  not an IPv4 port forward. Offer a separate LAN invitation with its LAN literal.
- Distinguish preparing, waiting for guest, connecting, connected, router setup
  needed, unreachable host, invitation rejected/expired/revoked, and disconnected.
  Never show a success state before authenticated tunnel readiness.
- On failure, explain private WAN address/double NAT/CGNAT as observations or
  suspected causes, not certain diagnosis from one failed port test. Offer home
  router instructions, supported direct IPv6, or switching which player hosts.
  External-VPN help is a separately selected last resort; no silent account or relay.

## 4. Router/firewall lifecycle and security limits

- Default automatic router mapping off. When explicitly requested, use a vetted
  IGD/PCP adapter to request only the encrypted TCP endpoint with a ten-minute
  renewable lease and unique ownership label. Reject existing mappings rather
  than replacing them. Verify the router honored the lease and destination.
  **First integration uses manual router guidance only.** The fake-adapter tests
  establish policy, not a chosen production IGD/PCP library. Automatic mapping is
  deferred until a separately reviewed adapter passes real-router ownership,
  renewal, crash-expiry and cleanup tests; it is not required for the first
  prerelease. Never present the current fake adapter as a working mapping feature.
- Renew only while hosting. Remove only a mapping still owned by this session;
  preserve mappings changed by users/other apps. If renewal or readback fails,
  report the failure and stop advertising a working public invitation. Do not
  turn a lease into a permanent mapping or open the raw/admin port.
- An elevated firewall helper creates only a tagged inbound rule scoped to the
  connector program, chosen interface/local address, TCP port and explicitly
  approved current profile. Do not disable the firewall or add a whole-program
  Any-profile/Any-interface exception. Remove owned rules on stop; track stale
  owned rules for reconciliation after crashes. Do not remove user rules.
- On interface/address change, pause admission, invalidate invites and reconcile
  old mappings/rules before asking the host to restart on the new network.
- Use separate pools for pending TLS handshakes (16) and authenticated streams
  (16). Release the pending slot on authentication success/failure and acquire a
  stream slot only after valid credentials; reject over-capacity promptly. Bound
  authentication time to 5 seconds and relay buffers to 256 KiB per direction;
  enforce backpressure. On orderly EOF propagate `CloseWrite`, allow up to 5 seconds
  to drain the opposite direction, then close both. Errors/revoke/stop close both
  immediately. Track the connection under its guest ID before opening the backend.
  Add per-source admission backoff, redact secrets, and test resource cleanup.
  These bounds reduce resource exhaustion; they are not DDoS protection.
- Keep helper secrets in memory. The service is a fixed game proxy, not a SOCKS
  proxy, LAN router, remote desktop service, or arbitrary TCP forwarder.

## 5. Packaging, compatibility and release gates

- Package the helper and modified engine as separately hashed components. Verify
  hashes before launch, include source and component notices, and run vulnerability
  checks on the exact dependency/compiler versions. Never embed a universal key.
  Initial target: Windows 10/11 x64, Go `windows/amd64`, `GOAMD64=v1`, `CGO_ENABLED=0`.
  ARM64 and 32-bit Windows remain unadvertised until the complete game bundle is
  tested. Toolchain verified here: `go version go1.27.3 windows/amd64`.
- Build the helper from its own standard-library-only module; do not inherit the
  investigation's WireGuard/gVisor dependencies. Ship updates with versioned manager
  bundles, hash manifest, compiler/version inventory and notices; no runtime plugin
  downloader. Check Go security releases before every prerelease and rebuild for
  applicable TLS/X.509 advisories. Use HTTPS release downloads and user-visible
  update installation after stopping the world; never auto-replace a running helper.
  Adjacent hashes detect mismatch/corruption, not compromise of the whole download;
  use signed release provenance where available and do not claim hashes are signatures.
- Version settings with a new connection mode; preserve existing addresses and
  names. Do not copy invitation secrets into persisted settings or upgrade old
  game worlds automatically. Preserve and test old save compatibility.
- Update the README: account-free default, one-time host router/firewall setup,
  private invitation sharing/revocation, direct-only limitations, and external-VPN
  fallback last. Keep public-game safety limits and experimental status visible.
- Add clean Windows 10/11 package tests, authenticated end-to-end real-engine tests,
  actual home IPv4/IPv6/router tests, and one-hour two-PC gameplay with save/restart.
  Wrong/expired/revoked invites, host impersonation, overload, crash and network
  change must fail safely. Independently attempt raw/admin access and unrelated
  laptop ports from another PC. Verify stop/uninstall cleanup and no lingering
  adapters/services. Obtain Gemini review of implementation and threat boundaries.
- Publish a new prerelease only after applicable gates pass and a normal user can
  complete the guest flow without an account, shell or configuration editing.
  Do not label the loopback investigation a completed WAN/gameplay test.
