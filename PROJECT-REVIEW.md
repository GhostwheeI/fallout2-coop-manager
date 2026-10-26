# Which Fallout 2 co-op engine does this use, and why?

Reviewed on **October 26, 2026** for an English Steam installation on a Windows
laptop hosting a two-person campaign. The manager pins the **stock, unmodified
gusmarcum v1.4.3 binaries**. It does not merge fixes from different engines.

## Recommendation

**gusmarcum/fallout2-coop v1.4.3 is the stronger starting point for a full
campaign.** That is an evidence-based preference, not a guarantee of stability.
Both projects are experimental and share much of the same multiplayer foundation.

The main reason is persistence and recovery: the fork adds protections against
host-client startup erasing visited-map state, improves reconnect behavior, and
fixes several campaign/script softlocks. It also provides player trading, team
revival, shared XP, rolling autosaves and quicksave/load. These matter more to
an ongoing campaign than star counts or version numbers.

## The two projects

| | [Cahb/fallout2-ce-coop](https://github.com/Cahb/fallout2-ce-coop) | [gusmarcum/fallout2-coop](https://github.com/gusmarcum/fallout2-coop) |
| --- | --- | --- |
| Release evaluated | [v0.4.1](https://github.com/Cahb/fallout2-ce-coop/releases/tag/v0.4.1), Oct 26, 2026 | [v1.4.3](https://github.com/gusmarcum/fallout2-coop/releases/tag/v1.4.3), Oct 14, 2026 |
| Relationship | Original dedicated-server co-op layer on Fallout 2 CE | Derived from Cahb v0.4, developed independently |
| Platforms | Windows and Linux release packages | Windows is the principal packaged target |
| Campaign completion | Shared vanilla campaign systems; not independently completed in this review | Maintainer reports Temple-to-Horrigan completion; not independently repeated in this review |
| Visited-map persistence | Lacks the fork's startup deletion guard and recovery component | Client guard plus server recovery for erased working map files |
| Reconnects | Shared hot-join foundation | Additional freeze/rejoin/combat-turn fixes |
| Team features | Independent player characters and synchronized world | Adds player trading, teammate revival, shared XP and recovery conveniences |
| Saves | Dedicated saves and autosaving | Five rotating autosave slots, F6/F7 and additional persistence fixes |
| Latest specific fixes | Worn-item transfer filtering, owned-container gating, non-host Modoc arrival and a map-entry script-error formatting fix | Broad v1.4.3 gameplay/script fixes; lacks two of Cahb's newest specific fixes |

## Source findings that influenced the choice

### Save integrity

In gusmarcum, [`src/loadsave.cc`](https://github.com/gusmarcum/fallout2-coop/blob/v1.4.3/src/loadsave.cc)
skips single-player map cleanup for a joining network client.
[`src/map_state_guard.cc`](https://github.com/gusmarcum/fallout2-coop/blob/v1.4.3/src/map_state_guard.cc)
also retains server-written working files and can replace files another program
erased. Cahb v0.4.1 lacks these protections. This can affect a campaign long
after the action that erased a visited map, so it is a significant practical concern.

The manager adds a further precaution: **the host's client and server use
separate directories**, with sanitized relative asset/save paths. Neither runs
from the original Steam directory.

### Campaign/script recovery

The fork contains targeted fixes for automatically opened dialogue getting stuck
without an authorized responder, the Horrigan encounter scene leaving the party
unable to continue, per-player poison/radiation behavior, and companion ownership
and placement. See its [changelog](https://github.com/gusmarcum/fallout2-coop/blob/v1.4.3/CHANGELOG.md)
and [bug notes](https://github.com/gusmarcum/fallout2-coop/tree/v1.4.3/bugs).

### Cahb's new fixes are real advantages

Cahb v0.4.1 filters equipped items out of container transfer selection. The
gusmarcum v1.4.3 transfer path still selects the first matching item PID without
that exclusion. When identical armor copies exist, a transfer can incorrectly
leave armor bonuses attached. Unequip armor before moving identical copies.

Cahb also runs the ownership/guard gate when opening owned containers normally.
That specific new gate is absent from gusmarcum v1.4.3. Do not assume every
shop/faction-owned container behaves exactly like single player.

Cahb's non-host Modoc arrival fix loops over all actor slots; the fork already
has a corresponding all-slot placement loop. A newer upstream release therefore
does not imply that all its changes are absent from the fork.

## Testing and evidence limits

This review inspected source checkouts, release metadata, changelogs, recent
issues, build workflows, test scripts and the actual downloaded Windows binaries.
Checksums were verified against GitHub release asset digests and Cahb's published
checksum file. Tests ran in throwaway copies of a locally licensed Steam game.

### Locally exercised on gusmarcum v1.4.3

| Scenario | Result |
| --- | --- |
| Character creation, including sex and age | 4/4 checks |
| Empty-server reconnect during a held combat turn | 9/9 checks |
| Party placement when the second player triggers a map transition | 2/2 checks |
| Companion following, elevation changes, and ownership after save/restart | 7/7 checks |
| Horrigan encounter scene and movement afterwards | 3/3 checks |
| New Reno stolen-car floor-trigger dialogue, both choices | 3/3 checks |
| First real-client join, creation screen, reconnect, F6 and server restart | 7/7 checks |

The first-client script needed debug logging enabled **only for the client** to
read its expected diagnostics from a release build. An initial run without that
logging reported failed assertions despite the server accepting the login and
the game drawing. This was a test setup issue; it is not counted as a gameplay
failure. Logging was not enabled for the live user's campaign.

The visited-map persistence test was also run. An early run overlapped another
visible-client test and hit the engine's single-instance limitation; its client
start/quit assertions failed. It was rerun sequentially. No campaign-completion
claim is based on the early failed run.

**The sequential rerun passed 21/21 checks:** visited maps remained visited,
killed plants stayed dead, quest state persisted, both maps were present in the
save, server restart and real-client exit preserved the state, and a temporary
random-encounter map was correctly removed on departure.

### Locally exercised on Cahb v0.4.1

The three native issue smoke checks were translated from the repository's Bash
driver to Windows Python sockets, without changing their intended commands or
assertions. All passed:

- Identical armor transfer preserves worn armor and its armor-class value.
- A non-host initiating Modoc arrival places both actors on the expected elevation.
- Plain opening of a guarded container triggers an ownership refusal.

The fork's newer persistence harness is not a valid universal test suite for
Cahb: it expects diagnostics and instrumentation Cahb does not provide. Its
failure to parse that engine is not treated as a gameplay regression.

### What the automated workflows prove

The fork has Windows/Linux build and static-analysis workflows. Its gameplay
regression scripts and Windows golden baselines exist, but those workflows do
**not** automatically run the full gameplay suite with proprietary game data.
README claims that tests pass on every commit are maintainer claims about their
local process, not independently visible CI campaign results.

Open issue counts also overstate unresolved defects in places: several issues
remain open although release notes describe fixes. Conversely, fewer reported
issues do not prove that an engine is more reliable.

## Important remaining limits

1. **Cross-elevation combat:** [issue #98](https://github.com/gusmarcum/fallout2-coop/issues/98)
   reports stalled/desynchronized combat when players split across floors.
   Keep everyone on the same floor, particularly before a fight.
2. **Quest quirks:** newer reports include
   [Laddie leading to the well](https://github.com/gusmarcum/fallout2-coop/issues/101),
   [Modoc night presentation](https://github.com/gusmarcum/fallout2-coop/issues/99),
   and [the Temple guard's inventory handling](https://github.com/gusmarcum/fallout2-coop/issues/94).
   Save before scripted sequences.
3. **One visible client per computer.** Test real clients sequentially on one laptop.
4. **One map/world party:** independent exploration across separate maps is not supported.
5. **No network authentication:** neither a player name nor a server name protects
   the listener. Use a private VPN. The manager disables the admin listener.
6. **No independent full campaign or remote-friend session was completed in this
   review.** Your actual second computer, connection and permissions still need
   a short end-to-end test.

## Gemini / Antigravity review

Gemini independently evaluated the supplied release/issue/source evidence and
also recommended gusmarcum v1.4.3. Its concrete objections informed the manager:
separate client/server directories, sanitized config paths, offline backups,
staged restores, completed-save confirmation before stopping, and asset
fingerprints. This review supplements tests; it does not replace them.

The release intentionally stays on a reproducible official engine build.
Backporting Cahb's newer fixes would create a third, locally maintained engine
variant and require its own multiplayer validation.
