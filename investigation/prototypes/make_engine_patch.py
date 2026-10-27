"""Generate a minimal source patch; never changes the checkout or shipped engine."""
import argparse
import difflib
import hashlib
from pathlib import Path


def generate(source, output):
    original = source.read_text(encoding="utf-8")
    needle = "addr.sin_addr.s_addr = htonl(INADDR_ANY);"
    if original.count(needle) != 2:
        raise ValueError("Expected exactly the game and admin listeners; re-review changed upstream source")
    changed = original.replace(needle, "addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);")
    delta = "".join(difflib.unified_diff(original.splitlines(True), changed.splitlines(True),
                      fromfile="a/src/server_net.cc", tofile="b/src/server_net.cc", n=1))
    output.write_text(delta, encoding="utf-8", newline="\n")
    return hashlib.sha256(source.read_bytes()).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print("Upstream source SHA256:", generate(args.source, args.output))
