import unittest
from router_mapping import SessionMapping


class FakeRouter:
    def __init__(self): self.entries = {}; self.ignore_lease = False
    def get(self, port): return self.entries.get(port)
    def add(self, port, value):
        self.entries[port] = dict(value)
        if self.ignore_lease: self.entries[port]["lease"] = 0
    def delete(self, port): del self.entries[port]


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.router = FakeRouter()
        self.mapping = SessionMapping(self.router, "192.0.2.5", 19302)
    def test_requires_consent(self):
        with self.assertRaises(PermissionError): self.mapping.open(consent=False, private_backend_verified=True)
        self.assertFalse(self.router.entries)
    def test_requires_private_backend(self):
        with self.assertRaises(PermissionError): self.mapping.open(consent=True, private_backend_verified=False)
        self.assertFalse(self.router.entries)
    def test_never_maps_raw_game_port(self):
        with self.assertRaises(ValueError): SessionMapping(self.router,"192.0.2.5",9300)
    def test_creates_finite_lease_and_cleans_owned_mapping(self):
        result = self.mapping.open(consent=True, private_backend_verified=True)
        self.assertEqual(result["lease"],600)
        self.mapping.close()
        self.assertFalse(self.router.entries)
    def test_preserves_existing_mapping(self):
        self.router.entries[19302] = {"description":"existing"}
        with self.assertRaises(ValueError): self.mapping.open(consent=True, private_backend_verified=True)
        self.assertEqual(self.router.entries[19302],{"description":"existing"})
    def test_preserves_replacement_mapping(self):
        self.mapping.open(consent=True, private_backend_verified=True)
        self.router.entries[19302]["description"] = "someone-else"
        self.mapping.close()
        self.assertIn(19302,self.router.entries)
    def test_rejects_router_that_ignores_lease_and_removes_own_entry(self):
        self.router.ignore_lease = True
        with self.assertRaises(ValueError): self.mapping.open(consent=True, private_backend_verified=True)
        self.assertFalse(self.router.entries)
    def test_close_is_idempotent(self):
        self.mapping.close(); self.mapping.close()
        self.assertFalse(self.router.entries)


if __name__ == "__main__": unittest.main(verbosity=2)
