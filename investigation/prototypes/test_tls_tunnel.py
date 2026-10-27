import asyncio
import base64
import json
import socket
import ssl
import time
import unittest

from tls_tunnel import Host, Connector, connect, parse_invite, tls_context, PREFIX


def altered(invite, **changes):
    raw = invite[len(PREFIX):]
    value = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    value.update(changes)
    return PREFIX + base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")


class TunnelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend_connections = 0
        self.backend_tasks = set()
        async def echo(reader, writer):
            self.backend_connections += 1
            task = asyncio.current_task()
            self.backend_tasks.add(task)
            try:
                while data := await reader.read(65536):
                    writer.write(data)
                    await writer.drain()
            finally:
                writer.close()
                await asyncio.gather(writer.wait_closed(), return_exceptions=True)
                self.backend_tasks.discard(task)
        self.backend = await asyncio.start_server(echo, "127.0.0.1", 0)
        self.host = Host(self.backend.sockets[0].getsockname()[1])
        await self.host.start()
        self.invite = self.host.invite()
        self.connector = None
        # Expected failed handshakes should not print tracebacks or diagnostics.
        self.loop = asyncio.get_running_loop()
        self.old_handler = self.loop.get_exception_handler()
        self.unexpected_errors = []
        def handler(loop, context):
            error = context.get("exception")
            if not isinstance(error, (ssl.SSLError, ConnectionResetError, ConnectionAbortedError)):
                self.unexpected_errors.append(type(error).__name__ + ": " + str(error))
        self.loop.set_exception_handler(handler)

    async def asyncTearDown(self):
        if self.connector:
            await self.connector.close()
        await self.host.close()
        self.backend.close()
        await self.backend.wait_closed()
        for task in list(self.backend_tasks):
            task.cancel()
        await asyncio.gather(*list(self.backend_tasks), return_exceptions=True)
        self.loop.set_exception_handler(self.old_handler)
        self.assertEqual(self.unexpected_errors, [])

    async def exchange(self, invitation=None, data=b"game-data"):
        reader, writer = await connect(invitation or self.invite)
        try:
            writer.write(data)
            await writer.drain()
            return await asyncio.wait_for(reader.readexactly(len(data)), 3)
        finally:
            writer.close()
            await asyncio.gather(writer.wait_closed(), return_exceptions=True)

    async def test_tls13_and_payload_roundtrip(self):
        reader, writer = await connect(self.invite)
        self.assertEqual(writer.get_extra_info("ssl_object").version(), "TLSv1.3")
        writer.write(b"hello")
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.readexactly(5), 3), b"hello")
        writer.close()
        await asyncio.gather(writer.wait_closed(), return_exceptions=True)

    async def test_unmodified_tcp_client_through_local_connector(self):
        self.connector = Connector(self.invite)
        await self.connector.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", self.connector.port)
        data = bytes(range(256)) * 4096
        writer.write(data)
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.readexactly(len(data)), 8), data)
        writer.close()
        await asyncio.gather(writer.wait_closed(), return_exceptions=True)

    async def test_wrong_key_rejected_before_backend_connection(self):
        with self.assertRaises((OSError, asyncio.IncompleteReadError, asyncio.TimeoutError)):
            await self.exchange(altered(self.invite, key="00" * 32))
        self.assertEqual(self.backend_connections, 0)

    async def test_unknown_identity_rejected(self):
        with self.assertRaises((OSError, asyncio.IncompleteReadError, asyncio.TimeoutError)):
            await self.exchange(altered(self.invite, identity="01" * 16))
        self.assertEqual(self.backend_connections, 0)

    async def test_expired_invitation_rejected_by_client(self):
        with self.assertRaises(ValueError):
            await connect(altered(self.invite, expires=int(time.time()) - 1))
        self.assertEqual(self.backend_connections, 0)

    async def test_expired_guest_rejected_by_host(self):
        identity = parse_invite(self.invite)["identity"]
        self.host.guests[identity].expires = 0
        with self.assertRaises((OSError, asyncio.IncompleteReadError, asyncio.TimeoutError)):
            await self.exchange()
        self.assertEqual(self.backend_connections, 0)

    async def test_revocation_closes_active_stream_and_blocks_reconnect(self):
        reader, writer = await connect(self.invite)
        writer.write(b"ok")
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.readexactly(2), 3), b"ok")
        identity = parse_invite(self.invite)["identity"]
        self.host.revoke(identity)
        self.assertEqual(await asyncio.wait_for(reader.read(1), 3), b"")
        writer.close()
        await asyncio.gather(writer.wait_closed(), return_exceptions=True)
        with self.assertRaises((OSError, asyncio.IncompleteReadError, asyncio.TimeoutError)):
            await self.exchange()

    async def test_individual_guest_revocation_does_not_revoke_other_guest(self):
        other = self.host.invite()
        self.host.revoke(parse_invite(self.invite)["identity"])
        self.assertEqual(await self.exchange(other), b"game-data")

    async def test_other_guest_key_cannot_impersonate_identity(self):
        other = parse_invite(self.host.invite())
        with self.assertRaises((OSError, asyncio.IncompleteReadError, asyncio.TimeoutError)):
            await self.exchange(altered(self.invite, key=other["key"]))
        self.assertEqual(self.backend_connections, 0)

    async def test_impersonated_host_cannot_authenticate(self):
        bad_host = Host(self.host.game_port)
        await bad_host.start()
        try:
            obj = parse_invite(self.invite)
            # Even knowing the guest's public identity does not provide its PSK.
            bad_host.invite()
            with self.assertRaises((OSError, asyncio.IncompleteReadError, asyncio.TimeoutError)):
                await self.exchange(altered(self.invite, port=bad_host.port))
        finally:
            await bad_host.close()

    async def test_tls_downgrade_rejected(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        with self.assertRaises(OSError):
            await asyncio.open_connection("127.0.0.1", self.host.port, ssl=context, server_hostname="invalid", ssl_handshake_timeout=2)

    async def test_prototype_will_not_listen_on_work_network(self):
        with self.assertRaises(ValueError):
            Host(self.host.game_port, "0.0.0.0")
        with self.assertRaises(ValueError):
            parse_invite(altered(self.invite, host="192.0.2.1"))

    async def test_invitation_validation_rejects_extra_destinations(self):
        for invalid in ("bad", PREFIX + "@", altered(self.invite, target_port=445), altered(self.invite, key="aa"), altered(self.invite, port=True)):
            with self.assertRaises(ValueError):
                parse_invite(invalid)

    async def test_stop_releases_listener_and_active_connections(self):
        port = self.host.port
        await self.host.close()
        with self.assertRaises(OSError):
            await asyncio.open_connection("127.0.0.1", port)

    async def test_wire_observer_sees_no_game_marker_or_invitation_secret(self):
        captured = bytearray()
        async def relay(reader, writer):
            remote_reader, remote_writer = await asyncio.open_connection("127.0.0.1", self.host.port)
            async def copy(src, dst):
                while data := await src.read(65536):
                    captured.extend(data)
                    dst.write(data); await dst.drain()
            tasks = [asyncio.create_task(copy(reader,remote_writer)), asyncio.create_task(copy(remote_reader,writer))]
            await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            writer.close(); remote_writer.close()
        tap = await asyncio.start_server(relay,"127.0.0.1",0)
        try:
            marker = b"F2-UNIQUE-GAME-PLAINTEXT-MARKER-123456"
            invitation = altered(self.invite,port=tap.sockets[0].getsockname()[1])
            self.assertEqual(await self.exchange(invitation,marker),marker)
            self.assertNotIn(marker,bytes(captured))
            self.assertNotIn(bytes.fromhex(parse_invite(self.invite)["key"]),bytes(captured))
        finally:
            tap.close(); await tap.wait_closed()

    async def test_ipv6_loopback_transport(self):
        if not socket.has_ipv6: self.skipTest("IPv6 unavailable")
        ipv6 = Host(self.host.game_port,"::1")
        try:
            try: await ipv6.start()
            except OSError: self.skipTest("IPv6 loopback disabled")
            self.assertEqual(await self.exchange(ipv6.invite()),b"game-data")
        finally:
            await ipv6.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
