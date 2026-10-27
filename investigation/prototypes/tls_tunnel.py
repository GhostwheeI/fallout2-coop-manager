"""Loopback-only pinned TLS 1.3 feasibility prototype. NOT production transport.

OpenSSL/Python TLS handles cryptography; this laptop's runtime is too old for a
public release. Invitations are bearer credentials: transmit them privately.
No credentials are logged or persisted; load_cert_chain uses short-lived temporary
PEM files, removed immediately after loading. The Go alternative avoids those files.
No router, firewall, adapter, service or released-manager changes are made.
"""
import asyncio
import base64
from dataclasses import dataclass
import ipaddress
import json
import secrets
import ssl
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
import time

PREFIX = "f2coop-test:"


@dataclass
class Guest:
    identity: str
    key: bytes
    expires: int
    revoked: bool = False


def loopback(host):
    if not ipaddress.ip_address(host).is_loopback:
        raise ValueError("Investigation prototype permits loopback endpoints only")
    return host


def parse_invite(value):
    if not isinstance(value, str) or len(value) > 8192 or not value.startswith(PREFIX):
        raise ValueError("Invalid invitation")
    try:
        raw = value[len(PREFIX):]
        obj = json.loads(base64.b64decode(raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True))
        if set(obj) != {"v", "host", "port", "identity", "key", "expires", "certificate"} or obj["v"] != 1:
            raise ValueError()
        loopback(obj["host"])
        if type(obj["port"]) is not int or not 1024 <= obj["port"] <= 65535:
            raise ValueError()
        if type(obj["expires"]) is not int or obj["expires"] <= time.time():
            raise ValueError("Invitation expired")
        identity, key = bytes.fromhex(obj["identity"]), bytes.fromhex(obj["key"])
        if len(identity) != 16 or len(key) != 32:
            raise ValueError()
        if not isinstance(obj["certificate"], str) or len(obj["certificate"]) > 4096:
            raise ValueError()
        return obj
    except (KeyError, TypeError, ValueError, UnicodeError) as error:
        raise ValueError("Invalid or expired invitation") from error


def tls_context(server=False):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if server else ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_3
    if server:
        context.num_tickets = 0
    else:
        # The invite pins the host's unique self-signed certificate as the only
        # trust anchor; a public CA and DNS name are intentionally unnecessary.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_REQUIRED
    return context


def host_certificate():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "F2 co-op investigation")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))
    return (cert.public_bytes(serialization.Encoding.PEM).decode(),
            key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()))


async def bridge(left_reader, left_writer, right_reader, right_writer):
    async def pump(reader, writer):
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    tasks = [asyncio.create_task(pump(left_reader, right_writer)),
             asyncio.create_task(pump(right_reader, left_writer))]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for writer in (left_writer, right_writer):
            writer.close()
        await asyncio.gather(*(w.wait_closed() for w in (left_writer, right_writer)), return_exceptions=True)


class Host:
    def __init__(self, game_port, host="127.0.0.1"):
        self.host = loopback(host)
        self.game_port = game_port  # Fixed local destination; never supplied by a guest.
        self.guests = {}
        self.active = {}
        self.server = None
        self.tasks = set()
        self.certificate, self.private_key = host_certificate()

    def credential_key(self, identity):
        guest = self.guests.get(identity)
        if guest and not guest.revoked and guest.expires > time.time():
            return guest.key
        return b""

    async def start(self):
        context = tls_context(server=True)
        with tempfile.TemporaryDirectory(prefix="f2-tls-investigation-") as directory:
            cert, key = Path(directory) / "cert.pem", Path(directory) / "key.pem"
            cert.write_text(self.certificate, encoding="ascii")
            key.write_bytes(self.private_key)
            context.load_cert_chain(cert, key)
        async def connected(reader, writer):
            task = asyncio.current_task()
            self.tasks.add(task)
            try:
                credentials = await asyncio.wait_for(reader.readexactly(48), 2)
                identity = credentials[:16].hex()
                expected = self.credential_key(identity)
                if not expected or not secrets.compare_digest(credentials[16:], expected):
                    return
                self.active.setdefault(identity, set()).add(writer)
                backend_reader, backend_writer = await asyncio.open_connection("127.0.0.1", self.game_port)
                await bridge(reader, writer, backend_reader, backend_writer)
            except (OSError, ValueError, asyncio.IncompleteReadError, asyncio.TimeoutError):
                pass
            finally:
                for streams in self.active.values():
                    streams.discard(writer)
                writer.close()
                await asyncio.gather(writer.wait_closed(), return_exceptions=True)
                self.tasks.discard(task)
        self.server = await asyncio.start_server(connected, self.host, 0, ssl=context, ssl_handshake_timeout=2)
        self.port = self.server.sockets[0].getsockname()[1]

    def invite(self, ttl=600):
        guest = Guest(secrets.token_hex(16), secrets.token_bytes(32), int(time.time()) + ttl)
        self.guests[guest.identity] = guest
        obj = dict(v=1, host=self.host, port=self.port, identity=guest.identity, key=guest.key.hex(), expires=guest.expires, certificate=self.certificate)
        return PREFIX + base64.urlsafe_b64encode(json.dumps(obj, separators=(",", ":")).encode()).decode().rstrip("=")

    def revoke(self, identity):
        self.guests[identity].revoked = True
        for stream in list(self.active.get(identity, ())):
            stream.close()

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*list(self.tasks), return_exceptions=True)


async def connect(invite):
    obj = parse_invite(invite)
    context = tls_context()
    context.load_verify_locations(cadata=obj["certificate"])
    reader, writer = await asyncio.wait_for(asyncio.open_connection(obj["host"], obj["port"], ssl=context, server_hostname="", ssl_handshake_timeout=2), 3)
    writer.write(bytes.fromhex(obj["identity"]) + bytes.fromhex(obj["key"]))
    await writer.drain()
    return reader, writer


class Connector:
    """Guest's unmodified game connects to this local TCP listener."""
    def __init__(self, invite):
        parse_invite(invite)
        self.invite = invite
        self.tasks = set()

    async def start(self):
        async def connected(reader, writer):
            task = asyncio.current_task()
            self.tasks.add(task)
            try:
                remote_reader, remote_writer = await connect(self.invite)
                await bridge(reader, writer, remote_reader, remote_writer)
            except (OSError, ValueError, asyncio.TimeoutError):
                pass
            finally:
                writer.close()
                await asyncio.gather(writer.wait_closed(), return_exceptions=True)
                self.tasks.discard(task)
        self.server = await asyncio.start_server(connected, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def close(self):
        self.server.close()
        await self.server.wait_closed()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*list(self.tasks), return_exceptions=True)
