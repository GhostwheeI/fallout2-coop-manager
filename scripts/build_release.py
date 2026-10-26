"""Build a shareable Windows release without including any user's game files."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
TAG = "v1.4.3"
ZIP_NAME = "fallout2-coop-v1.4.3-windows.zip"
ZIP_HASH = "a46781291e053b87cecaf1409ead5d3ff2cdf2782d5497b9dba39454b0628f89"
URL = f"https://github.com/gusmarcum/fallout2-coop/releases/download/{TAG}/{ZIP_NAME}"


def build():
    if sys.platform != "win32":
        raise SystemExit("Build the Windows package on Windows.")
    downloads = ROOT / "downloads"
    downloads.mkdir(exist_ok=True)
    archive = downloads / ZIP_NAME
    if not archive.exists():
        print("Downloading the pinned upstream release…", flush=True)
        urllib.request.urlretrieve(URL, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ZIP_HASH:
        raise SystemExit("Upstream archive checksum mismatch. Build stopped.")
    payload = downloads / "gusmarcum-v1.4.3"
    payload.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        # The verified upstream archive has a flat layout. Never extract arbitrary paths.
        for member in package.infolist():
            if not member.is_dir() and Path(member.filename).name == member.filename:
                (payload / member.filename).write_bytes(package.read(member))
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "manager"), "-p", "test_core.py", "-v"], check=True)
    output = ROOT / "package"
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed",
        "--name", "Fallout 2 Co-op Manager", "--distpath", str(output),
        "--workpath", str(ROOT / "build" / "manager"), "--specpath", str(ROOT / "manager"),
        "--paths", str(ROOT / "manager"), "--add-data", f"{payload};engine", str(ROOT / "manager" / "app.py")], check=True)
    for name in ("START-HERE.txt", "README.md", "PROJECT-REVIEW.md", "LICENSE", "THIRD-PARTY-NOTICES.md"):
        shutil.copy2(ROOT / name, output / name)
    shutil.copytree(ROOT / "third_party", output / "third_party", dirs_exist_ok=True)
    runtime = output / "third_party" / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    for path in Path(sys.base_prefix).glob("LICENSE*"):
        shutil.copy2(path, runtime / ("Python-" + path.name))
    for folder in (Path(sys.base_prefix) / "tcl").glob("*"):
        if folder.is_dir():
            for pattern in ("license*", "LICENSE*", "COPYING*"):
                for path in folder.glob(pattern):
                    if path.is_file():
                        shutil.copy2(path, runtime / (folder.name + "-" + path.name))
    distribution = importlib.metadata.distribution("pyinstaller")
    for relative in distribution.files:
        if str(relative).replace("\\", "/").endswith("licenses/COPYING.txt"):
            shutil.copy2(distribution.locate_file(relative), runtime / "PyInstaller-COPYING.txt")
    # Python's Windows distribution does not always ship Tcl's standalone license.
    # Keep a source copy alongside the notices when preparing a release.
    if not any("tcl8.6" in p.name for p in runtime.iterdir()):
        bundled_tcl_notice = ROOT / "third_party" / "Tcl-license.terms"
        if not bundled_tcl_notice.exists():
            urllib.request.urlretrieve("https://raw.githubusercontent.com/tcltk/tcl/core-8-6-branch/license.terms", bundled_tcl_notice)
        shutil.copy2(bundled_tcl_notice, runtime / "Tcl-license.terms")
    exe = output / "Fallout 2 Co-op Manager.exe"
    subprocess.run([str(exe), "--self-check"], check=True, timeout=60)
    report = output / "manager-self-check.json"
    if not report.exists() or json.loads(report.read_text())["engine_checksums"] != "verified":
        raise SystemExit("Packaged application self-check did not finish.")
    report.unlink()
    # Explicit allowlist: never recursively archive the working directory.
    files = [output / name for name in ("Fallout 2 Co-op Manager.exe", "START-HERE.txt", "README.md", "PROJECT-REVIEW.md", "LICENSE", "THIRD-PARTY-NOTICES.md")]
    files += [p for p in (output / "third_party").rglob("*") if p.is_file()]
    artifact = ROOT / "Fallout2-Coop-Manager-v0.1.0-Windows.zip"
    with zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            bundle.write(path, "Fallout2-Coop-Manager/" + path.relative_to(output).as_posix())
    sums = ROOT / "SHA256SUMS.txt"
    sums.write_text(hashlib.sha256(artifact.read_bytes()).hexdigest() + "  " + artifact.name + "\n", encoding="utf-8")
    print(f"Built {artifact} ({artifact.stat().st_size / 1024**2:.1f} MB)")


if __name__ == "__main__":
    build()

