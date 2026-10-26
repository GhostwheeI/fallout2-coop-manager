"""Fallout 2 Co-op launcher: portable Windows menu and guided setup."""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import queue
import socket
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import traceback
import webbrowser

from core import (VERSION, RELEASE_URL, MESHNET_URL, Installation, ServerProcess,
                  base_directory, discover_steam_games, launch_client, sha256,
                  validate_address, validate_player)

BG, PANEL, FG, MUTED, ACCENT = "#111b19", "#1b2925", "#e2e8d8", "#adbaac", "#f0c66c"


class Manager(tk.Tk):
    def __init__(self, root=None):
        super().__init__()
        self.title("Fallout 2 Co-op · Play together")
        self.geometry("1040x780")
        self.minsize(920, 700)
        self.configure(background=BG)
        self.installation = Installation(Path(root) if root else base_directory())
        self.events = queue.Queue(maxsize=3000)
        self.server = ServerProcess(self.installation, self.emit)
        self.client = None
        self.busy = False
        self.last_save_seen = 0
        self.approved = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready to set up")
        self.vars = {}
        for key, value in self.installation.config.items():
            self.vars[key] = tk.BooleanVar(value=value) if isinstance(value, bool) else tk.StringVar(value=str(value))
        if not self.vars["source"].get():
            found = discover_steam_games()
            if found:
                self.vars["source"].set(str(found[0]))
        self.style_ui()
        self.build_ui()
        self.show("home")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.report_callback_exception = self.on_exception
        self.after(150, self.tick)

    def style_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=FG, font=("Segoe UI", 11))
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Title.TLabel", foreground=ACCENT, font=("Consolas", 26, "bold"))
        style.configure("Heading.TLabel", foreground=ACCENT, font=("Segoe UI", 15, "bold"))
        style.configure("TButton", padding=(14, 9), background=PANEL, foreground=FG, borderwidth=1)
        style.map("TButton", background=[("active", "#33483b"), ("disabled", "#18201c")])
        style.configure("Menu.TButton", padding=(22, 16), anchor="w", font=("Segoe UI", 13))
        style.configure("Accent.TButton", background="#526039", foreground="#ffffff")
        style.configure("TEntry", fieldbackground="#26372e", foreground=FG, insertcolor=FG, padding=7)
        style.configure("TCombobox", fieldbackground="#26372e", foreground=FG, padding=6)
        style.map("TCombobox", fieldbackground=[("readonly", "#26372e")], foreground=[("readonly", FG)])
        style.configure("TCheckbutton", background=BG, foreground=FG, padding=5)
        style.map("TCheckbutton", background=[("active", BG)], foreground=[("active", FG)])

    def label(self, parent, text, style="TLabel", **kwargs):
        widget = ttk.Label(parent, text=text, style=style, wraplength=680, justify="left", **kwargs)
        widget.pack(anchor="w", pady=5)
        return widget

    def button(self, parent, text, command, **kwargs):
        widget = ttk.Button(parent, text=text, command=command, **kwargs)
        widget.pack(anchor="w", pady=5)
        return widget

    def entry(self, parent, text, key, width=55):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=text, width=22).pack(side="left")
        widget = ttk.Entry(row, textvariable=self.vars[key], width=width)
        widget.pack(side="left", fill="x", expand=True)
        return widget

    def page(self, name, heading, subtitle):
        frame = ttk.Frame(self.content)
        self.pages[name] = frame
        self.label(frame, heading, "Title.TLabel")
        self.label(frame, subtitle, "Muted.TLabel")
        return frame

    def build_ui(self):
        wrapper = ttk.Frame(self, padding=24)
        wrapper.pack(fill="both", expand=True)
        head = ttk.Frame(wrapper)
        head.pack(fill="x")
        ttk.Label(head, text="FALLOUT 2  /  CO-OP", foreground=ACCENT, font=("Consolas", 13, "bold")).pack(side="left")
        ttk.Label(head, text=VERSION, style="Muted.TLabel").pack(side="right")
        ttk.Separator(wrapper).pack(fill="x", pady=14)
        body = ttk.Frame(wrapper)
        body.pack(fill="both", expand=True)
        nav = ttk.Frame(body, width=190)
        nav.pack(side="left", fill="y", padx=(0, 22))
        for title, name in [("Main menu", "home"), ("Host a game", "host"), ("Join a game", "join"),
                            ("Saves & backups", "saves"), ("Connection guide", "network"), ("Server log", "logs")]:
            ttk.Button(nav, text=title, command=lambda n=name: self.show(n), width=19).pack(fill="x", pady=4)
        self.label(nav, "Local game files stay\non your laptop.", "Muted.TLabel")
        viewport = ttk.Frame(body)
        viewport.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(viewport, background=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=self.canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.content = ttk.Frame(self.canvas)
        content_window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(content_window, width=event.width))
        self.bind_all("<MouseWheel>", lambda event: self.canvas.yview_scroll(-int(event.delta / 120), "units") if event.widget.winfo_class() not in ("Text", "TCombobox") else None)
        self.pages = {}
        home = self.page("home", "Play together.", "Choose what you'd like to do. The next screen walks you through it.")
        self.button(home, "START DEDICATED SERVER\nHost a world for you and your friend", lambda: self.show("host"), style="Menu.TButton", width=52)
        self.button(home, "CONNECT TO DEDICATED SERVER\nJoin your friend's world", lambda: self.show("join"), style="Menu.TButton", width=52)
        self.button(home, "SAVES & BACKUPS\nKeep a copy of your shared adventure", lambda: self.show("saves"), style="Menu.TButton", width=52)
        self.label(home, "First time? Your Steam copy supplies the game data. This manager prepares a separate co-op copy automatically.", "Muted.TLabel")
        self.label(home, "Before your campaign", "Heading.TLabel")
        self.label(home, "Stay together on the same floor, especially in combat. Press F6 to quicksave before difficult quests. Both players must use this same co-op version.")
        self.button(home, "Read the project comparison", self.open_review)
        host = self.page("host", "Host a world", "Keep this laptop on while you play. Your friend joins the world running here.")
        self.setup_section(host)
        self.label(host, "2  Choose your world", "Heading.TLabel")
        self.save_choice = tk.StringVar(value="New game — Temple of Trials")
        self.save_combo = ttk.Combobox(host, textvariable=self.save_choice, state="readonly", width=60)
        self.save_combo.pack(fill="x", pady=4)
        self.entry(host, "World name", "server_name")
        self.entry(host, "Game port", "port", width=8)
        row = ttk.Frame(host)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Difficulty", width=22).pack(side="left")
        self.game_diff = ttk.Combobox(row, values=["Easy", "Normal", "Hard"], state="readonly", width=14)
        self.game_diff.current(int(self.installation.config["game_difficulty"]))
        self.game_diff.pack(side="left")
        ttk.Label(row, text="  Combat ").pack(side="left")
        self.combat_diff = ttk.Combobox(row, values=["Easy", "Normal", "Hard"], state="readonly", width=14)
        self.combat_diff.current(int(self.installation.config["combat_difficulty"]))
        self.combat_diff.pack(side="left")
        options = ttk.Frame(host)
        options.pack(fill="x", pady=2)
        ttk.Checkbutton(options, text="Share experience", variable=self.vars["shared_xp"]).pack(side="left")
        ttk.Label(options, text="   Autosave every (seconds)").pack(side="left")
        ttk.Entry(options, textvariable=self.vars["autosave"], width=6).pack(side="left")
        self.label(host, "3  Start when you're on your home network", "Heading.TLabel")
        ttk.Checkbutton(host, text="I'm on a home or approved network, with private access configured.", variable=self.approved).pack(anchor="w")
        self.label(host, "The server listens on all adapters. Use Meshnet and a firewall rule scoped to your friend. The admin port stays off.", "Muted.TLabel")
        controls = ttk.Frame(host)
        controls.pack(fill="x")
        self.start_button = ttk.Button(controls, text="Start server", style="Accent.TButton", command=self.start_server)
        self.start_button.pack(side="left", padx=(0, 6))
        self.stop_button = ttk.Button(controls, text="Stop & back up", command=self.stop_server)
        self.stop_button.pack(side="left", padx=6)
        ttk.Button(controls, text="Join my server", command=self.join_own).pack(side="left", padx=6)
        join = self.page("join", "Join a world", "The host starts the server first. You'll create your own character when you connect.")
        self.setup_section(join)
        self.label(join, "2  Your character and connection", "Heading.TLabel")
        self.entry(join, "Your player name", "player")
        self.label(join, "Use the same name every time to get your character back. Choose a different name from your friend.", "Muted.TLabel")
        self.entry(join, "Server address", "address")
        self.label(join, "Use the host's Meshnet IPv4 address or Nord name. On the host laptop, use 127.0.0.1:9300.", "Muted.TLabel")
        ttk.Checkbutton(join, text="Play in a window", variable=self.vars["windowed"]).pack(anchor="w", pady=6)
        controls = ttk.Frame(join)
        controls.pack(fill="x", pady=8)
        ttk.Button(controls, text="Connect & play", style="Accent.TButton", command=self.join_game).pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="Test connection", command=self.test_connection).pack(side="left")
        self.label(join, "If it won't connect", "Heading.TLabel")
        self.label(join, "Check that both devices are linked in Meshnet and the host has allowed your device remote access. Confirm the server is running and the address is correct. Open Connection guide for the steps.")
        self.button(join, "Open connection guide", lambda: self.show("network"))
        saves = self.page("saves", "Keep your adventure", "Backups are made with the server stopped so the files stay consistent.")
        self.label(saves, "F6 writes the shared quicksave to slot 16. Autosaves rotate through slots 11–15. F7 loads the quicksave for everyone.")
        self.slot_list = tk.Listbox(saves, height=7, background=PANEL, foreground=FG, selectbackground="#56633a", borderwidth=0, font=("Consolas", 11))
        self.slot_list.pack(fill="x", pady=12)
        row = ttk.Frame(saves)
        row.pack(fill="x")
        for title, command in [("Refresh", self.refresh_saves), ("Back up now", self.backup), ("Restore backup…", self.restore)]:
            ttk.Button(row, text=title, command=command).pack(side="left", padx=(0, 7))
        self.button(saves, "Open backups folder", lambda: self.open_folder("Backups"))
        self.label(saves, "Stopping safely", "Heading.TLabel")
        self.label(saves, "In game, press F6 and wait for the saved message. Wait at least 10 seconds, then have everyone quit. Use Stop & back up. The manager cannot force a save while the admin port is disabled.")
        self.label(saves, "The manager backs up the previous world before a server start and again after a stop. It keeps every backup; you control when to remove old ones.", "Muted.TLabel")
        network = self.page("network", "Connect your friend", "NordVPN's Meshnet provides a private path between your laptops. No router forwarding is needed.")
        for title, body in [
            ("1  Do this at home", "Keep hosting off while you're on a work or other network where you aren't authorized to run a server."),
            ("2  Link the two devices", "Both players open NordVPN → Devices in Meshnet and enable Meshnet. Invite your friend's own Nord account; they accept. The manager won't send invitations for you."),
            ("3  Allow the game connection", "On the host, allow that friend's device remote access in Meshnet. File sharing, traffic routing and access to the rest of your LAN aren't needed for this game. If Windows Firewall blocks the game, allow only TCP 9300 for f2_server.exe from your friend's Meshnet IP."),
            ("4  Share your Meshnet address", "Copy your laptop's Meshnet IPv4 address or Nord name from NordVPN. Enter it below, then copy the joining instructions. The host joins locally; your friend uses your Meshnet address."),
        ]:
            self.label(network, title, "Heading.TLabel")
            self.label(network, body)
        self.entry(network, "Your Meshnet address", "share_address")
        row = ttk.Frame(network)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="Copy joining instructions", command=self.copy_invite).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Open Nord's setup guide", command=lambda: webbrowser.open(MESHNET_URL)).pack(side="left")
        self.label(network, "Router forwarding: the project advises against exposing its unauthenticated game port. Prefer Meshnet. This manager never changes router or firewall settings.", "Muted.TLabel")
        logs = self.page("logs", "Server log", "Live activity and save confirmations. A copy is kept in the Logs folder.")
        self.log_view = tk.Text(logs, background="#0b120f", foreground="#b9d39f", font=("Consolas", 10), wrap="word", borderwidth=0, state="disabled")
        self.log_view.configure(height=22)
        self.log_view.pack(fill="both", expand=True, pady=12)
        self.button(logs, "Open log folder", lambda: self.open_folder("Logs"))
        ttk.Separator(wrapper).pack(fill="x", pady=(12, 6))
        ttk.Label(wrapper, textvariable=self.status, style="Muted.TLabel").pack(anchor="w")

    def setup_section(self, parent):
        self.label(parent, "1  Prepare your game", "Heading.TLabel")
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Entry(row, textvariable=self.vars["source"]).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=self.browse_source).pack(side="left", padx=6)
        ttk.Button(row, text="Prepare", command=self.prepare).pack(side="left")
        self.label(parent, "Steam is detected automatically. Original game files stay untouched. First setup copies about 600 MB per role.", "Muted.TLabel")

    def show(self, name):
        for frame in self.pages.values():
            frame.pack_forget()
        self.pages[name].pack(fill="both", expand=True)
        self.canvas.yview_moveto(0)
        if name in ("host", "saves"):
            self.refresh_saves()

    def browse_source(self):
        folder = filedialog.askdirectory(title="Select your original Steam Fallout 2 folder")
        if folder:
            self.vars["source"].set(folder)

    def capture(self):
        if self.busy:
            raise ValueError("Please wait for the current operation to finish.")
        cfg = self.installation.config
        previous = dict(cfg)
        for key, var in self.vars.items():
            cfg[key] = var.get()
        cfg["port"] = int(cfg["port"])
        cfg["autosave"] = int(cfg["autosave"])
        cfg["game_difficulty"] = self.game_diff.current()
        cfg["combat_difficulty"] = self.combat_diff.current()
        if self.server.running() and any(previous[k] != cfg[k] for k in ("port", "server_name", "autosave", "game_difficulty", "combat_difficulty", "shared_xp")):
            self.installation.config = previous
            raise ValueError("Stop the server before changing server settings.")
        self.installation.server_env(None)  # Validate server configuration without starting it.
        self.installation.save_config()

    def emit(self, text):
        try:
            self.events.put_nowait(("log", text))
        except queue.Full:
            pass  # Full output is still in the log file; keep the UI responsive.

    def work(self, fn, done=None):
        if self.busy:
            messagebox.showinfo("Working", "Please wait for the current operation to finish.")
            return
        self.busy = True
        self.status.set("Working…")
        def run():
            try:
                result = fn()
                self.events.put(("done", (done, result)))
            except Exception as error:
                self.events.put(("error", str(error)))
        threading.Thread(target=run, daemon=True).start()

    def prepare(self):
        if self.server.running():
            messagebox.showinfo("Server running", "Stop the server before preparing game files.")
            return
        self.capture()
        source = Path(self.vars["source"].get())
        self.work(lambda: self.installation.prepare(source, "client", self.emit),
                  lambda _: messagebox.showinfo("Ready", "Your co-op game is ready. Continue with hosting or joining."))

    def refresh_saves(self):
        rows = self.installation.saves()
        values = [f"Slot {r['slot']:02d} · {datetime.fromtimestamp(r['time']):%b %d, %H:%M:%S}" for r in rows]
        self.save_values = {label: row["slot"] for label, row in zip(values, rows)}
        values.append("New game — Temple of Trials")
        self.save_combo["values"] = values
        if self.save_choice.get() not in values or (rows and self.save_choice.get().startswith("New game")):
            self.save_combo.current(0)
        self.slot_list.delete(0, "end")
        if not rows:
            self.slot_list.insert("end", "No shared saves yet. Your campaign has not started.")
        for row in rows:
            kind = "quicksave" if row["slot"] == 16 else "autosave" if row["slot"] >= 11 else "manual"
            self.slot_list.insert("end", f"Slot {row['slot']:02d}  {datetime.fromtimestamp(row['time']):%Y-%m-%d %H:%M:%S}  {kind}")

    def start_server(self):
        if self.busy or self.server.running():
            return
        if not self.approved.get():
            messagebox.showinfo("Connection setup", "Start hosting at home or on a network where hosting is approved. Finish the Connection guide, then check the box on this screen.")
            return
        self.capture()
        slot = self.save_values.get(self.save_choice.get())
        if slot is None and self.installation.saves():
            if not messagebox.askyesno("Start a new world?", "A backup of the existing world will be made first. A new world replaces the rotating autosaves as you play. Start over?"):
                return
        source = Path(self.vars["source"].get())
        def start():
            self.installation.prepare(source, "server", self.emit)
            backup = self.installation.backup()
            if backup:
                self.emit(f"Before-start backup: {backup.name}")
            self.server.start(slot)
            time.sleep(2)
            if not self.server.running():
                raise RuntimeError("The server exited during startup. See Server log for the reason.")
        self.work(start, lambda _: self.show("logs"))

    def join_own(self):
        if not self.server.running():
            messagebox.showinfo("Start first", "Start the dedicated server first, then use Join my server.")
            return
        self.vars["address"].set(f"127.0.0.1:{self.installation.config['port']}")
        self.show("join")

    def join_game(self):
        self.capture()
        validate_player(self.vars["player"].get())
        validate_address(self.vars["address"].get())
        if self.client and self.client.poll() is None:
            messagebox.showinfo("Already running", "Your game is already running. Switch to the game window.")
            return
        source = Path(self.vars["source"].get())
        address, player = self.vars["address"].get(), self.vars["player"].get()
        def join():
            self.installation.prepare(source, "client", self.emit)
            return launch_client(self.installation, address, player)
        def launched(process):
            self.client = process
            self.emit(f"Game launched as {player} at {address}.")
        self.work(join, launched)

    def test_connection(self):
        host, port = validate_address(self.vars["address"].get())
        def test():
            with socket.create_connection((host, port), timeout=5) as connection:
                connection.settimeout(5)
                preamble = b""
                while len(preamble) < 10:
                    chunk = connection.recv(10 - len(preamble))
                    if not chunk:
                        break
                    preamble += chunk
                if not preamble.startswith(b"F2NS"):
                    raise ValueError("The port responded, but it did not identify as a Fallout 2 co-op server.")
            return f"Reached the Fallout 2 server at {host}:{port}. This checks the connection; Connect & play checks the full game session."
        self.work(test, lambda text: messagebox.showinfo("Connection works", text))

    def stop_server(self, closing=False):
        if self.busy:
            return False
        if not self.server.running():
            return True
        if self.server.online:
            messagebox.showinfo("Players still connected", "Press F6 in game, wait for the saved message, and have everyone quit before stopping. The server still has connected clients.")
            return False
        if not messagebox.askyesno("Save before stopping", "Press F6 in the game and wait for the saved message. Wait 10 seconds, then have everyone quit the game.\n\nHave you done that? Stopping uses the last completed save; it does not create a new save."):
            return False
        def stop():
            # A completed save log follows the write. Avoid immediately terminating after it.
            wait = 10 - (time.monotonic() - self.server.last_save_output)
            if wait > 0:
                self.emit("Waiting for the recent save to settle…")
                time.sleep(wait)
            self.server.stop()
            path = self.installation.backup()
            self.emit(f"Server stopped. Backup: {path.name if path else 'no saves yet'}")
        self.work(stop, lambda _: self.destroy() if closing else self.refresh_saves())
        return True

    def backup(self):
        if self.server.running():
            messagebox.showinfo("Stop first", "Use Stop & back up on the Host screen. Backups need a stopped server.")
            return
        self.work(self.installation.backup, lambda path: messagebox.showinfo("Backup", str(path) if path else "There are no shared saves yet."))

    def restore(self):
        if self.server.running():
            messagebox.showinfo("Stop first", "Stop the server before restoring a backup.")
            return
        archive = filedialog.askopenfilename(title="Choose a manager backup", initialdir=self.installation.root / "Backups", filetypes=[("World backups", "*.zip")])
        if archive and messagebox.askyesno("Restore world?", "The current world will be backed up first, then replaced with the selected backup. Continue?"):
            self.work(lambda: self.installation.restore(Path(archive)), lambda _: self.refresh_saves())

    def copy_invite(self):
        host, port = validate_address(self.vars["share_address"].get(), int(self.vars["port"].get()))
        text = (f"Fallout 2 Co-op — {VERSION}\n\nUnzip the manager into a writable folder on your laptop. Install your own English Steam Fallout 2.\n"
                "Open Fallout 2 Co-op Manager.exe → Connect to dedicated server. The manager finds and prepares your game.\n"
                f"Choose your own player name (use it every time). Server address: {host}:{port}\n"
                "Both devices must be linked in NordVPN Meshnet, with remote access allowed by the host.\n"
                "Choose Connect & play after the host starts the server.\n"
                "F6 quicksaves the shared world; F7 reloads it for everyone. Stay together on the same floor during combat.\n"
                f"Official release: {RELEASE_URL}\n")
        fingerprint = self.installation.root / "game-data-fingerprint.json"
        if fingerprint.exists():
            value = json.loads(fingerprint.read_text(encoding="utf-8"))["fingerprint"]
            text += f"Game data fingerprint (compare with your game-data-fingerprint.json): {value}\n"
        self.clipboard_clear()
        self.clipboard_append(text)
        self.installation.config["share_address"] = self.vars["share_address"].get()
        self.installation.save_config()
        (self.installation.root / "JOINING-INSTRUCTIONS.txt").write_text(text, encoding="utf-8")
        messagebox.showinfo("Copied", "Joining instructions copied. Send them and the original manager ZIP to your friend. Do not send your Play or World folders.")

    def open_folder(self, name):
        path = self.installation.root / name
        path.mkdir(exist_ok=True)
        os.startfile(path)

    def open_review(self):
        path = self.installation.root / "PROJECT-REVIEW.md"
        if path.exists():
            os.startfile(path)
        else:
            webbrowser.open(RELEASE_URL)

    def tick(self):
        for _ in range(150):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.log_view.configure(state="normal")
                self.log_view.insert("end", value + "\n")
                if int(self.log_view.index("end-1c").split(".")[0]) > 2500:
                    self.log_view.delete("1.0", "200.0")
                self.log_view.see("end")
                self.log_view.configure(state="disabled")
            elif kind == "done":
                self.busy = False
                callback, result = value
                if callback:
                    callback(result)
            elif kind == "error":
                self.busy = False
                messagebox.showerror("Couldn't finish", value)
        if not self.busy:
            running = self.server.running()
            self.status.set(f"Server {'running on port ' + str(self.installation.config['port']) if running else 'stopped'}  ·  Game {'running' if self.client and self.client.poll() is None else 'closed'}  ·  {VERSION}")
        self.start_button.configure(state="disabled" if self.busy or self.server.running() else "normal")
        self.stop_button.configure(state="normal" if self.server.running() and not self.busy else "disabled")
        self.after(150, self.tick)

    def close(self):
        if self.busy:
            messagebox.showinfo("Working", "Please let the current operation finish before closing.")
            return
        if self.server.running():
            self.stop_server(closing=True)
        else:
            self.destroy()

    def on_exception(self, exc, value, tb):
        self.busy = False
        folder = self.installation.root / "Logs"
        folder.mkdir(exist_ok=True)
        (folder / "manager-error.log").write_text("".join(traceback.format_exception(exc, value, tb)), encoding="utf-8")
        messagebox.showerror("Couldn't finish", str(value))


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        from core import bundled_engine, verify_engine
        verify_engine(bundled_engine())
        output = base_directory() / "manager-self-check.json"
        output.write_text(json.dumps({"version": VERSION, "engine_checksums": "verified", "tkinter": tk.TkVersion}), encoding="utf-8")
    else:
        try:
            if sys.platform == "win32":
                import ctypes
                from ctypes import wintypes
                import hashlib
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.CreateMutexW.restype = wintypes.HANDLE
                kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
                mutex_name = "Local\\Fallout2CoopManager-" + hashlib.sha256(str(base_directory()).lower().encode()).hexdigest()[:24]
                instance_mutex = kernel.CreateMutexW(None, False, mutex_name)
                if not instance_mutex:
                    raise OSError("Could not create the manager instance lock.")
                if ctypes.get_last_error() == 183:
                    messagebox.showinfo("Already open", "The manager is already open for this folder. Switch to its existing window.")
                    sys.exit(0)
            Manager().mainloop()
        except Exception as error:
            messagebox.showerror("Fallout 2 Co-op Manager", str(error))
