"""Portable Fallout 2 Co-op setup and process management. Standard library only."""
from __future__ import annotations

import hashlib
import configparser
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime

VERSION = "gusmarcum v1.4.3"
RELEASE_URL = "https://github.com/gusmarcum/fallout2-coop/releases/tag/v1.4.3"
MESHNET_URL = "https://meshnet.nordvpn.com/getting-started/how-to-start-using-meshnet/using-meshnet-on-windows"
ENGINE_HASHES = {
    "f2_server.exe": "c5c3be3a23abd3481a6794a8831b189b529fd2ab0972515d250588daef12b755",
    "fallout2-ce.exe": "aa5ca9361010fde34a0faab2534006a5fd2676440703021bf20e90ab72b19351",
}
DEFAULTS = {"player": "", "address": "127.0.0.1:9300", "share_address": "",
            "port": 9300, "server_name": "Fallout 2 with friends", "autosave": 300,
            "game_difficulty": 1, "combat_difficulty": 1, "shared_xp": True,
            "source": "", "windowed": True}


def base_directory() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def bundled_engine() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "engine"
    return base_directory() / "downloads" / "gusmarcum-v1.4.3"


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def validate_player(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,31}", value):
        raise ValueError("Choose a name with 1–31 letters, numbers, hyphens or underscores. No spaces. Your name retrieves your character next time.")
    return value


def validate_address(value: str, default_port: int = 9300) -> tuple[str, int]:
    value = value.strip()
    match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9.-]*)(?::([0-9]{1,5}))?", value)
    if not match:
        raise ValueError("Enter the host's Meshnet IPv4 address or Nord name, optionally followed by :9300.")
    host = match[1]
    port = int(match[2] or default_port)
    if not 1024 <= port <= 65535:
        raise ValueError("Use a game port between 1024 and 65535.")
    return host, port


def clean_environment() -> dict[str, str]:
    # A test flag inherited from another session must never alter a live campaign.
    return {k: v for k, v in os.environ.items() if not k.upper().startswith("F2_") and k.upper() not in {"SDL_VIDEODRIVER", "SDL_AUDIODRIVER", "DEBUGACTIVE"}}


def discover_steam_games() -> list[Path]:
    roots = [Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Steam"]
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                roots.insert(0, Path(winreg.QueryValueEx(key, "SteamPath")[0]))
        except OSError:
            pass
    libraries = list(roots)
    for root in roots:
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            for value in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="replace")):
                libraries.append(Path(value.replace("\\\\", "\\")))
    found = []
    for library in libraries:
        install_name = "Fallout 2"
        manifest = library / "steamapps" / "appmanifest_38410.acf"
        if manifest.exists():
            match = re.search(r'"installdir"\s+"([^"]+)"', manifest.read_text(encoding="utf-8", errors="replace"))
            if match:
                install_name = match[1]
        game = library / "steamapps" / "common" / install_name
        if valid_source(game) and game not in found:
            found.append(game)
    return found


def valid_source(path: Path) -> bool:
    return all((path / name).is_file() for name in ("master.dat", "critter.dat", "patch000.dat"))


def verify_engine(path: Path) -> None:
    for name, expected in ENGINE_HASHES.items():
        if not (path / name).is_file() or sha256(path / name) != expected:
            raise ValueError(f"{name} does not match the pinned official {VERSION} release. Re-extract the manager package.")


def asset_fingerprint(game: Path) -> dict[str, str]:
    """Include loose game overrides; DAT hashes alone cannot detect leftover mods."""
    hashes = {name: sha256(game / name) for name in ("master.dat", "critter.dat", "patch000.dat")}
    data = game / "data"
    for path in sorted(data.rglob("*")):
        relative = path.relative_to(game).as_posix().lower()
        if path.is_file() and not path.is_symlink() and not relative.startswith("data/savegame/") and not relative.endswith((".sav", "automap.db")):
            hashes[relative] = sha256(path)
    joined = json.dumps(hashes, sort_keys=True).encode()
    return {"fingerprint": hashlib.sha256(joined).hexdigest(), **hashes}


def write_local_config(source: Path, destination: Path) -> None:
    config = configparser.ConfigParser(interpolation=None, strict=False)
    if source.exists():
        config.read(source, encoding="utf-8-sig")
    for section in ("system", "sound", "preferences"):
        if not config.has_section(section):
            config.add_section(section)
    for key, value in {"master_dat": "master.dat", "critter_dat": "critter.dat", "master_patches": "data", "critter_patches": "data", "language": "english"}.items():
        config.set("system", key, value)
    config.set("sound", "music_path1", "sound/music/")
    config.set("sound", "music_path2", "sound/music/")
    with destination.open("w", encoding="utf-8") as output:
        config.write(output)


class Installation:
    def __init__(self, root: Path, payload: Path | None = None):
        self.root = root.resolve()
        self.payload = payload or bundled_engine()
        self.settings_path = self.root / "manager-settings.json"
        self.config = dict(DEFAULTS)
        if self.settings_path.exists():
            try:
                loaded = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict):
                    raise ValueError("Settings must be a JSON object")
                self.config.update({k: v for k, v in loaded.items() if k in DEFAULTS})
            except (OSError, ValueError, TypeError):
                shutil.copy2(self.settings_path, self.settings_path.with_suffix(".invalid.json"))

    def directory(self, role: str) -> Path:
        if role not in ("client", "server"):
            raise ValueError("Unknown installation role")
        return self.root / ("Play" if role == "client" else "World")

    def save_config(self) -> None:
        temporary = self.settings_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.config, indent=2), encoding="utf-8")
        temporary.replace(self.settings_path)

    def ready(self, role: str) -> bool:
        directory = self.directory(role)
        return valid_source(directory) and (directory / "fallout2.cfg").exists() and all((directory / name).exists() for name in ENGINE_HASHES)

    def prepare(self, source: Path, role: str, log=print) -> None:
        source = source.resolve()
        destination = self.directory(role)
        if self.ready(role):
            verify_engine(destination)
            write_local_config(destination / "fallout2.cfg", destination / "fallout2.cfg")
            fingerprint = asset_fingerprint(destination)
            (self.root / "game-data-fingerprint.json").write_text(json.dumps(fingerprint, indent=2), encoding="utf-8")
            log(f"{destination.name} is already prepared; existing saves kept.")
            return
        if not valid_source(source):
            raise ValueError("Select an English Fallout 2 installation containing master.dat, critter.dat and patch000.dat.")
        if source == destination.resolve() or destination.resolve().is_relative_to(source):
            raise ValueError("Select your original Steam game folder, outside the manager folder.")
        verify_engine(self.payload)
        destination.mkdir(parents=True, exist_ok=True)
        # Never overwrite a partial installation's saved campaign.
        if (destination / "data" / "SAVEGAME").exists() or any(p.suffix.lower() == ".sav" for p in (destination / "data").rglob("*")):
            raise ValueError("This incomplete installation contains saves. Back it up and select a fresh manager folder before preparing it.")
        for name in ("master.dat", "critter.dat", "patch000.dat"):
            log(f"Copying {name} for {role}…")
            shutil.copy2(source / name, destination / name)
        for name in ("data", "sound"):
            if (source / name).is_dir():
                log(f"Copying {name}…")
                def ignore_runtime(folder, names):
                    return [n for n in names if n.upper() == "SAVEGAME" or n.lower().endswith(".sav") or n.upper() == "AUTOMAP.DB"]
                shutil.copytree(source / name, destination / name, dirs_exist_ok=True, ignore=ignore_runtime)
        # Steam's original executable, ddraw.dll, sfall and high-res hooks are intentionally not copied.
        write_local_config(source / "fallout2.cfg", destination / "fallout2.cfg")
        for name in ENGINE_HASHES:
            shutil.copy2(self.payload / name, destination / name)
        for name in ("LICENSE.md", "AUTHORS.md", "README.md", "CHANGELOG.md"):
            if (self.payload / name).exists():
                shutil.copy2(self.payload / name, destination / name)
        (destination / "coop-version.txt").write_text(VERSION, encoding="utf-8")
        fingerprint = asset_fingerprint(destination)
        (self.root / "game-data-fingerprint.json").write_text(json.dumps(fingerprint, indent=2), encoding="utf-8")
        self.config["source"] = str(source)
        self.save_config()
        log(f"Ready: {destination}")

    def saves(self) -> list[dict]:
        rows = []
        for path in (self.directory("server") / "data" / "SAVEGAME").glob("SLOT*/SAVE.DAT"):
            match = re.fullmatch(r"SLOT(\d+)", path.parent.name, re.I)
            if match and 1 <= int(match[1]) <= 16:
                rows.append({"slot": int(match[1]), "time": path.stat().st_mtime, "path": path})
        return sorted(rows, key=lambda row: row["time"], reverse=True)

    def server_env(self, slot: int | None) -> dict[str, str]:
        cfg = self.config
        port = int(cfg["port"])
        validate_address(f"127.0.0.1:{port}")
        autosave = int(cfg["autosave"])
        if autosave != 0 and not 30 <= autosave <= 86400:
            raise ValueError("Autosave must be 0 (disabled) or 30–86400 seconds.")
        for field in ("game_difficulty", "combat_difficulty"):
            if int(cfg[field]) not in (0, 1, 2):
                raise ValueError("Difficulty must be Easy, Normal or Hard.")
        if not 1 <= len(cfg["server_name"]) <= 80 or any(c in cfg["server_name"] for c in "\r\n"):
            raise ValueError("Use a server name of 1–80 characters on one line.")
        env = clean_environment()
        env.update(F2_SERVER_NET=str(port), F2_SERVER_NAME=cfg["server_name"],
                   F2_SERVER_PACE_MS="100", F2_AUTOSAVE_SECS=str(autosave),
                   F2_SERVER_KEEPALIVE="1", F2_GAME_DIFFICULTY=str(cfg["game_difficulty"]),
                   F2_COMBAT_DIFFICULTY=str(cfg["combat_difficulty"]), F2_SERVER_DEBUG_LOG="1",
                   F2_PARTY_XP="1" if cfg["shared_xp"] else "0")
        # No admin listener. Upstream binds it to all adapters with no password.
        if slot is None:
            env["F2_SERVER_MAP"] = "artemple.map"
        else:
            if slot not in [row["slot"] for row in self.saves()]:
                raise ValueError("That save slot is empty.")
            env["F2_SERVER_LOAD"] = str(slot)
        return env

    def client_env(self, address: str, player: str) -> dict[str, str]:
        host, port = validate_address(address, int(self.config["port"]))
        env = clean_environment()
        env.update(F2_CLIENT_CONNECT=f"{host}:{port}", F2_PLAYER_NAME=validate_player(player), F2_PLAYER_CREATE="ask")
        if self.config["windowed"]:
            env["F2_WINDOWED"] = "1"
        return env

    def backup(self) -> Path | None:
        world = self.directory("server")
        files = [p for p in (world / "data" / "SAVEGAME").rglob("*") if p.is_file()]
        files += list((world / "data" / "MAPS").glob("*.SAV"))
        files += list((world / "data" / "maps").glob("*.sav"))
        files = sorted(set(files))
        if not files:
            return None
        destination = self.root / "Backups"
        destination.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
        archive = destination / f"Fallout2-world_{stamp}.zip"
        temporary = archive.with_suffix(".zip.partial")
        try:
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as output:
                for path in files:
                    if path.is_symlink() or not path.resolve().is_relative_to(world.resolve()):
                        raise ValueError("Save path leaves this installation")
                    output.write(path, path.relative_to(world).as_posix())
            with zipfile.ZipFile(temporary) as check:
                if check.testzip() is not None:
                    raise ValueError("Backup verification failed.")
            temporary.replace(archive)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return archive

    def restore(self, archive: Path) -> None:
        world = self.directory("server")
        if not self.ready("server"):
            raise ValueError("Prepare a server first.")
        with zipfile.ZipFile(archive) as source:
            if not any(re.fullmatch(r"data/savegame/slot\d+/save\.dat", info.filename.replace("\\", "/"), re.I) for info in source.infolist()):
                raise ValueError("This archive contains no saved campaign.")
            if sum(info.file_size for info in source.infolist()) > 1024 ** 3:
                raise ValueError("Backup is too large.")
            members = []
            seen = set()
            for info in source.infolist():
                path = Path(info.filename.replace("\\", "/"))
                parts = [p.lower() for p in path.parts]
                if path.is_absolute() or ".." in parts or ":" in info.filename or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("This archive is not a manager world backup.")
                if info.is_dir():
                    if parts == ["data"] or parts in (["data", "savegame"], ["data", "maps"]):
                        continue
                    if len(parts) >= 3 and parts[:2] == ["data", "savegame"] and re.fullmatch(r"slot\d{1,2}", parts[2]):
                        continue
                    raise ValueError("Unexpected backup directory.")
                allowed = bool(len(parts) >= 4 and parts[:2] == ["data", "savegame"] and re.fullmatch(r"slot\d{1,2}", parts[2]))
                allowed |= len(parts) == 3 and parts[:2] == ["data", "maps"] and parts[2].endswith(".sav")
                if not allowed:
                    raise ValueError("This archive is not a manager world backup.")
                canonical = Path("data", *[p.upper() for p in path.parts[1:]])
                if canonical in seen:
                    raise ValueError("Duplicate backup file.")
                seen.add(canonical)
                members.append((info, canonical))
            # Validate and extract fully before changing the installed world.
            with tempfile.TemporaryDirectory(dir=self.root, prefix="restore-") as staging:
                staging = Path(staging)
                for info, relative in members:
                    target = staging / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with source.open(info) as incoming, target.open("wb") as output:
                        shutil.copyfileobj(incoming, output)
                self.backup()
                # Build the whole replacement MAPS directory before swapping anything.
                maps = world / "data" / "MAPS"
                next_maps = staging / "next-maps"
                if maps.exists():
                    if not maps.resolve().is_relative_to(world.resolve()) or maps.is_symlink():
                        raise ValueError("Map directory leaves this world.")
                    shutil.copytree(maps, next_maps)
                    for path in next_maps.iterdir():
                        if path.suffix.lower() == ".sav":
                            path.unlink()
                else:
                    next_maps.mkdir()
                if (staging / "data" / "MAPS").exists():
                    shutil.copytree(staging / "data" / "MAPS", next_maps, dirs_exist_ok=True)
                completed = []
                try:
                    for name, replacement in (("SAVEGAME", staging / "data" / "SAVEGAME"), ("MAPS", next_maps)):
                        target = world / "data" / name
                        if target.is_symlink() or not target.resolve().is_relative_to(world.resolve()):
                            raise ValueError("Save directory leaves this world.")
                        rollback = staging / ("previous-" + name)
                        existed = target.exists()
                        if existed:
                            target.replace(rollback)
                        completed.append((target, rollback, existed))
                        replacement.replace(target)
                except Exception:
                    for target, rollback, existed in reversed(completed):
                        if target.exists():
                            target.replace(staging / ("failed-" + target.name))
                        if existed:
                            rollback.replace(target)
                    raise


class ServerProcess:
    def __init__(self, installation: Installation, emit):
        self.installation = installation
        self.emit = emit
        self.process = None
        self.log_file = None
        self.online = 0
        self.last_output = time.monotonic()
        self.last_save_output = 0.0

    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, slot: int | None) -> None:
        if self.running():
            raise ValueError("The server is already running.")
        folder = self.installation.directory("server")
        verify_engine(folder)
        # Refuse to collide with another server. This is a local port check, not a firewall change.
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", int(self.installation.config["port"]))) == 0:
                raise ValueError("That port is already in use. Stop the other server or choose another port.")
        env = self.installation.server_env(slot)
        self.online = 0
        self.last_save_output = 0.0
        logs = self.installation.root / "Logs"
        logs.mkdir(exist_ok=True)
        self.log_file = (logs / f"server-{datetime.now():%Y%m%d-%H%M%S}.log").open("w", encoding="utf-8")
        try:
            self.process = subprocess.Popen([str(folder / "f2_server.exe")], cwd=folder, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            self.log_file.close()
            raise
        import threading
        process, log_file = self.process, self.log_file
        def reader():
            try:
                for line in process.stdout:
                    self.last_output = time.monotonic()
                    count = re.search(r"^f2_server: (?:client (?:connected|joined mid-stream) \((\d+) total\)|client dropped \([^)]*\), (\d+) remain)", line)
                    if count:
                        self.online = int(count[1] or count[2])
                    if "save: wrote slot" in line.lower():
                        self.last_save_output = time.monotonic()
                    log_file.write(line)
                    log_file.flush()
                    self.emit(line.rstrip())
                self.emit(f"Server exited (code {process.wait()}).")
            finally:
                self.online = 0
                log_file.close()
        threading.Thread(target=reader, daemon=True).start()

    def stop(self) -> None:
        # Upstream offers no safe local shutdown IPC with its admin socket disabled.
        # The UI explicitly asks users to F6 and confirm the save before terminating.
        if self.running():
            if self.online:
                raise ValueError("Players are still connected. Quicksave and have everyone quit first.")
            # With no clients the simulation gate freezes the world. Wait for any
            # final beat/write to finish before terminating the idle stock binary.
            quiet_at = time.monotonic()
            while time.monotonic() - quiet_at < 3:
                if self.online:
                    raise ValueError("A player connected while stopping. Ask them to quit.")
                if self.last_output > quiet_at:
                    quiet_at = self.last_output
                time.sleep(.1)
            self.process.terminate()
            self.process.wait(timeout=15)


def launch_client(installation: Installation, address: str, player: str):
    folder = installation.directory("client")
    verify_engine(folder)
    return subprocess.Popen([str(folder / "fallout2-ce.exe")], cwd=folder,
        env=installation.client_env(address, player), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
