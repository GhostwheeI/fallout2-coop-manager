# Fallout 2 Co-op Manager

**A Windows game menu that helps you and a friend play Fallout 2 together.**

Start a dedicated server, connect to a friend's world, prepare your Steam game
files, and keep backups from one desktop app. Numbered setup screens guide you
through each step. The download runs without installing Python.

[**Download the Windows ZIP**](https://github.com/GhostwheeI/fallout2-coop-manager/releases/latest)
· [Host a game](#host-a-game)
· [Join a game](#join-a-game)
· [Connection help](#play-over-the-internet)
· [Troubleshooting](#troubleshooting)

> **Early release:** the manager is new, and the underlying co-op engine is
> experimental. Keep backups. Before committing to a long campaign, test a
> save, full server restart, and reconnect with your friend. Local checks have
> passed; a live two-computer session over Meshnet has not yet been field-tested.

## What this does

The main menu has three starting points:

| Menu option | What happens next |
| --- | --- |
| **Start dedicated server** | Prepare the host's game files, choose a new or saved world, set difficulty and autosaves, then start the server. |
| **Connect to dedicated server** | Prepare the player's game files, enter a persistent player name and the host's address, then launch Fallout 2. |
| **Saves & backups** | Inspect saves, create an offline backup, or restore an earlier backup. |

Additional screens explain internet connections and display the live server log.

The manager:

- Finds Fallout 2 in the default Steam library or additional Steam libraries.
- Copies required assets into its own folders; your original Steam game stays untouched.
- Uses separate **Play** and **World** folders on the host, keeping client files away from the server's working saves.
- Verifies the bundled co-op executables against pinned SHA-256 hashes.
- Keeps the server's unauthenticated admin port disabled.
- Creates a backup before a world starts and after it stops.
- Produces joining instructions you can copy and send to a friend.
- Records a game-data fingerprint to help compare both players' installations.

It does **not** include Fallout 2 game data, change your router/firewall, send
invitations, or sign in to NordVPN for you. Network permissions need your attention.

## What you need

- Windows 10 or 11, 64-bit.
- Your own installed **English Steam copy of Fallout 2**. Each player needs their own copy.
- About **650 MB extra space to join**, or **1.3 GB to host and play**,
  plus room for saves and backups.
- The **same manager release** on both computers.
- For internet play: a private connection between the computers. The guide
  uses **NordVPN Meshnet**; another suitable private VPN can also work.

The tested configuration is the English Steam game with vanilla data. Restoration
Project, RPU, Expansion, sfall hook-script mods, other languages and other asset
sets are not verified by this manager. Start with a clean Steam installation.

## Install once

1. Open [Releases](https://github.com/GhostwheeI/fallout2-coop-manager/releases/latest).
2. Download **`Fallout2-Coop-Manager-v0.1.0-Windows.zip`**.
3. **Extract the entire ZIP** into a writable folder. Do not run the app from
   inside the ZIP or place it inside your original Steam game folder.
4. Open **`Fallout 2 Co-op Manager.exe`**.
5. Choose **Start dedicated server** or **Connect to dedicated server**.

No Python, terminal commands or administrator access are required for the manager.
Windows may identify this new, unsigned executable as an unrecognized application.
Download from this repository's release page and verify the published checksum
before deciding whether to run it. You can also [build from source](#run-or-build-from-source).

<details>
<summary>How to verify the download with PowerShell</summary>

Download `SHA256SUMS.txt` from the same release. In the folder containing the ZIP:

```powershell
Get-FileHash .\Fallout2-Coop-Manager-v0.1.0-Windows.zip -Algorithm SHA256
```

Compare the hash with `SHA256SUMS.txt`. They should match exactly; letter case
does not matter. The checksum identifies the release file, not a security audit.

</details>

## Host a game

The host runs **two programs**: a dedicated server that owns the world, and a
game client to play in it. The manager handles launching both.

1. Choose **Start dedicated server**.
2. Under **Prepare your game**, check the detected Steam folder. Use **Browse**
   if it is wrong. Choose **Prepare** to prepare your local player copy.
3. Choose **New game — Temple of Trials** or select a saved slot. Existing
   saves are listed newest first, with their date and time.
4. Set the world name, difficulty, shared experience and autosave interval.
   The defaults are Normal difficulty, shared experience and a five-minute autosave.
5. Complete the **Connection guide**. Host only at home or on a network where
   running a server is approved, then check the corresponding box.
6. Choose **Start server**. On first use, the manager prepares a separate
   **World** folder for the dedicated server.
7. Choose **Host a game → Join my server**. Enter your player name and choose
   **Connect & play**. Your local server address is **`127.0.0.1:9300`**.
8. Give your friend the **same release ZIP** and the instructions from
   **Connection guide → Copy joining instructions**.

Keep the manager and server running while anyone plays. Closing the game client
does not stop the server. A server with nobody connected pauses the world.

### Your player name is your character

Use the **same player name every time** to return to your character. Use a name
different from your friend's. Names accept 1–31 letters, numbers, hyphens or
underscores, without spaces. A name the server has not seen before creates a
new character.

This identity is **not a password**. Restrict access to people you trust through
your private network.

## Join a game

1. Install your own English Steam copy of Fallout 2.
2. Extract the same manager ZIP as the host and open the manager.
3. Choose **Connect to dedicated server**.
4. Check the detected Steam folder and choose **Prepare**. First use copies
   the required game files automatically; it does not modify Steam's copy.
5. Enter your own persistent **player name**.
6. Enter the **host's Meshnet IPv4 address or Nord name**. Add `:9300` if the
   address does not already include a port. Do not use `127.0.0.1` on the
   friend's computer; that address means their own computer.
7. Once the host has started the server, choose **Test connection**, then
   **Connect & play**.
8. Create your character when prompted. On later sessions, use the same name.

The connection test confirms that a Fallout 2 server answers. It does not prove
that game data, the full session or latency are correct.

## Play over the internet

### Recommended: NordVPN Meshnet

Ordinary NordVPN browsing servers do not provide inbound port forwarding.
**Meshnet is a separate feature** that links your devices privately. Nord's
[current gaming guide](https://meshnet.nordvpn.com/how-to/gaming) describes
private game connections without router forwarding.

1. Both players open NordVPN and turn on **Devices in Meshnet**.
2. The host invites the friend's own Nord account. The friend accepts.
3. On the host, allow the friend's device **remote access** in Meshnet.
   Traffic routing, file sharing and access to the host's wider LAN are not
   needed for this game.
4. Copy the host laptop's **Meshnet IPv4 address or Nord name** from NordVPN.
5. In the manager's **Connection guide**, enter that address and copy the
   joining instructions.
6. If Windows Firewall blocks the server, configure a rule limited to
   **`World\f2_server.exe`, TCP port 9300, and your friend's Meshnet IP**.
   A custom port must match the manager's game-port setting.
   The `World` folder is created on first server preparation/start; if it does
   not exist yet, complete the Meshnet steps, start the server at home, then
   configure the scoped firewall rule before your friend connects.

The manager guides these steps but does not change security settings or send
Meshnet invitations. Follow Nord's official
[Windows setup guide](https://meshnet.nordvpn.com/getting-started/how-to-start-using-meshnet/using-meshnet-on-windows)
and [remote-access permission guide](https://meshnet.nordvpn.com/features/explaining-permissions/remote-access-permissions)
for the current app layout.

### Router forwarding and work networks

The upstream project advises against exposing the game port directly to the
internet: its protocol has no authentication. **Use a private VPN instead of
public port forwarding**, even if your router can restrict source addresses.
The admin listener remains disabled in this manager.

Do not enable hosting on a work network without authorization. Preparation,
configuration and reading the guide work while the server is stopped. The
network checkbox is a reminder, not a firewall or a network detector.

## Save, stop and resume

| Key / feature | What it does |
| --- | --- |
| **F6** | Quicksaves the shared server world to slot **16**. |
| **F7** | Loads that quicksave for **every player**. Coordinate before using it. |
| Autosaves | Rotate through slots **11–15**, normally every five minutes and on map changes. |
| **Stop & back up** | Stops the server after your confirmation, then backs up the existing saved state. It does **not** create a fresh in-game save. |

To finish a session:

1. In game, press **F6** and wait for the saved confirmation.
2. Wait at least **10 seconds**.
3. Have **everyone quit their game client**.
4. In the manager, choose **Host a game → Stop & back up**.

The manager refuses to stop while it sees connected clients. Because the stock
engine has no private local shutdown control with its admin port disabled, the
manager terminates the idle server after a quiet period. **Unsaved actions are
not preserved.** Keep the explicit save-and-quit routine above.

Next session, choose the newest appropriate saved slot and start the server.
Both players reconnect with their original names.

### Restore a backup

With the server stopped, open **Saves & backups → Restore backup…** and select
a manager backup ZIP. The current saved world is backed up before replacement.
Restores validate archive paths and stage files before swapping save directories.
Keep a separate copy of valuable backups outside the working folder too.

Backups are never automatically deleted. Monitor disk space over long campaigns.

## Known gameplay limitations

This launcher cannot repair engine bugs. The pinned engine is
**[gusmarcum/fallout2-coop v1.4.3](https://github.com/gusmarcum/fallout2-coop/releases/tag/v1.4.3)**.

- **Keep the party on the same floor, particularly during combat.**
  [Upstream issue #98](https://github.com/gusmarcum/fallout2-coop/issues/98)
  reports combat desynchronization and inactive enemies when players split across elevations.
- The party shares one world and travels together. This is campaign co-op,
  not an MMO or independently explorable multi-map server.
- The engine allows **one visible game client per computer**.
- Duplicate armor transfers can leave incorrect armor bonuses. **Unequip
  armor before transferring identical copies to a container or companion.**
  Cahb's newer v0.4.1 fixes this; the selected gusmarcum release lacks that fix.
- Some quest scripting and ownership checks differ from single player.
  Examples and the reasons for the engine choice are in [PROJECT-REVIEW.md](PROJECT-REVIEW.md).
- Restoration Project and sfall hook-script mods are not supported by the
  chosen upstream engine.

Both players should run the same version and identical game data. The generated
`game-data-fingerprint.json` includes the main DAT files and loose data overrides;
compare its `fingerprint` value if your installations behave differently.
It is a diagnostic record, not a network-enforced compatibility check.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Steam folder was not found | Install Fallout 2, then use **Browse** to select the folder containing `master.dat`, `critter.dat`, and `patch000.dat`. |
| “Select an English Fallout 2 installation” | Choose the original game folder, not `steamapps`, the ZIP, or an unprepared manager folder. |
| Friend cannot connect | Start the host server first. Check Meshnet linking, remote-access permission, host address, port and the host's scoped firewall rule. |
| Connection works, game closes | Close another Fallout 2 client on the same computer. Confirm both players use the same package and game data. Check **Server log** and `Play\debug.log` if present. |
| A new character appears | Check the player name. A different name is a different account. Check that the host loaded the expected save. |
| Server says the port is in use | Stop the other server or choose another port on the Host screen. The joining address must use that same port. |
| Stop button says players are connected | Save with F6, wait, then have everyone quit. Give disconnects a moment to appear in the log. |
| Combat stops after using stairs | Get the party back onto the same floor if possible; otherwise restart from an earlier save. See issue #98 above. |
| Backup or restore fails | Stop the server, check free disk space and folder write access, and keep the original backup. Do not delete the only working save. |
| Windows warns about an unknown publisher | This release is unsigned. Verify the download source/checksum or build it yourself. |

For a manager bug, [open an issue](https://github.com/GhostwheeI/fallout2-coop-manager/issues)
with the manager/engine version, Windows version, steps to reproduce and the relevant
log excerpt. Remove personal addresses and names before posting logs. Report gameplay
engine bugs to the appropriate upstream project, with its requested reproduction details.

## Where your files live

Everything created by the manager lives beside the executable:

```text
Fallout2-Coop-Manager/
  Fallout 2 Co-op Manager.exe
  Play/                         Your local game client and copied assets
  World/                        Host-only server, copied assets and shared saves
    data/SAVEGAME/              Save slots
  Backups/                      Offline world backup ZIPs
  Logs/                         Server output and manager error reports
  manager-settings.json         Local preferences, name and addresses
  game-data-fingerprint.json     Game-data comparison record
```

To share with someone else, send the **original release ZIP**, not your working
folder. Your working folders contain copyrighted assets, private settings and saves.

## Run or build from source

Source runs require Python 3.13 with Tkinter on Windows. The application itself
uses only Python's standard library. Building requires PyInstaller.

```powershell
git clone https://github.com/GhostwheeI/fallout2-coop-manager.git
cd fallout2-coop-manager
python -m pip install -r requirements-build.txt
python scripts/build_release.py
```

The build script downloads the **pinned** upstream engine archive, verifies its
SHA-256, runs manager tests, packages the executable, checks the packaged engine
hashes, and creates the public ZIP using an explicit allowlist. It never packages
`Play`, `World`, settings, logs or saves. Output is the release ZIP and `SHA256SUMS.txt`.

After a build downloads the engine, you can run the source UI directly:

```powershell
python manager/app.py
python -m unittest discover -s manager -p test_core.py -v
```

The Windows workflow builds the package and publishes a workflow artifact on
pushes and pull requests. It tests manager behavior and packaging; it does not
run a Fallout 2 campaign or include proprietary game assets.

## Project status and credits

This is a new, **AI-assisted** manager. Codex wrote the initial implementation;
Gemini/Antigravity reviewed the engine choice and manager core. Targeted engine
tests used a local licensed Steam installation. This is not a claim of a complete
independent campaign playthrough or a security certification.

The multiplayer engine is the work of
[gusmarcum and contributors](https://github.com/gusmarcum/fallout2-coop), building
on [Cahb's co-op implementation](https://github.com/Cahb/fallout2-ce-coop) and
[Alexander Batalov and Fallout 2 Community Edition contributors](https://github.com/alexbatalov/fallout2-ce).
Fallout 2 is the work of Black Isle Studios / Interplay.

Manager source: **MIT**. Bundled engine: its separate **Sustainable Use License**,
including non-commercial distribution restrictions. See
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). This fan project is unaffiliated
with the original game publishers, Steam or NordVPN.
