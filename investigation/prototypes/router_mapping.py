"""Mapping policy prototype. Adapter-injected; NEVER discovers or calls a router.

An implementation must connect this to a vetted IGD/PCP library after home tests.
This prototype proves ownership/consent/finite-lease behavior using a fake adapter.
"""
import secrets


class SessionMapping:
    def __init__(self, router, local_address, tunnel_port, raw_game_port=9300):
        if tunnel_port == raw_game_port or not 1024 <= tunnel_port <= 65535:
            raise ValueError("Only a separate encrypted tunnel endpoint may be mapped")
        self.router = router
        self.address, self.port = local_address, tunnel_port
        self.owner = "f2coop-" + secrets.token_hex(12)
        self.lease = 600
        self.mapping = None

    def open(self, *, consent, private_backend_verified):
        if not consent or not private_backend_verified:
            raise PermissionError("Explicit consent and private-backend verification required")
        if self.router.get(self.port) is not None:
            raise ValueError("Port already mapped; existing mappings will not be replaced")
        expected = dict(address=self.address, port=self.port, description=self.owner, lease=self.lease)
        self.router.add(self.port, expected)
        actual = self.router.get(self.port)
        self.mapping = expected
        if actual != expected:
            self.close()
            raise ValueError("Router did not honor the finite owned mapping; use manual setup")
        return actual

    def close(self):
        if self.mapping:
            actual = self.router.get(self.port)
            # Never delete a mapping replaced by the user or another application.
            if actual and all(actual.get(k) == self.mapping[k] for k in ("address", "port", "description")):
                self.router.delete(self.port)
            self.mapping = None
