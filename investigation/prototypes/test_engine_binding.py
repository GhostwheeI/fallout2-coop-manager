import asyncio
import socket
import tempfile
from pathlib import Path
import unittest
from make_engine_patch import generate


class BindTests(unittest.TestCase):
    def test_patch_changes_both_listeners_without_modifying_source(self):
        source = Path(__file__).resolve().parents[2] / "review" / "gusmarcum" / "src" / "server_net.cc"
        # The local checkout is optional: public CI can still run socket tests.
        if not source.exists():
            source = Path(__file__).resolve().parents[3] / "review" / "gusmarcum" / "src" / "server_net.cc"
        if not source.exists(): self.skipTest("Engine source checkout not supplied")
        before = source.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "loopback.patch"
            generate(source,out)
            patch = out.read_text()
            self.assertEqual(patch.count("+    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);"),2)
        self.assertEqual(source.read_bytes(),before)

    def test_winsock_loopback_binding_is_private(self):
        # An OS binding proof, NOT a test of a rebuilt engine.
        with socket.socket() as listener:
            listener.bind(("127.0.0.1",0)); listener.listen()
            self.assertEqual(listener.getsockname()[0],"127.0.0.1")
            with socket.create_connection(listener.getsockname(),timeout=1): pass
            addresses = socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET)
            for address in {row[4][0] for row in addresses if not row[4][0].startswith("127.")}:
                with socket.socket() as probe:
                    probe.settimeout(.5)
                    self.assertNotEqual(probe.connect_ex((address,listener.getsockname()[1])),0)
