"""Go's provider session follows the original A lease across HTTP tool steps."""
import hashlib
import unittest
from unittest.mock import patch

from test_go_application_handler_composition import NativeApplicationHTTPFixture


class GoApplicationSessionTests(NativeApplicationHTTPFixture):
    def test_original_turn_reuses_one_session_and_other_turn_gets_another(self):
        observed = []
        exchange = self.router._application_exchange

        def capture(request, **kwargs):
            observed.append({key.lower(): value for key, value in request.header_items()})
            return exchange(request, **kwargs)

        with patch.object(self.router, "_application_exchange", capture):
            self.assertEqual(self.request(turn="original", step="step-a",
                headers={"x-opencode-session": "caller-spoof", "User-Agent": "OpenCode"})[0], 200)
            self.assertEqual(self.request(turn="original", step="step-b")[0], 200)
            self.assertEqual(self.request(path="/application-turns/close", payload={"turn_id": "original"})[0], 200)
            self.assertEqual(self.request(turn="independent", step="step-c")[0], 200)
        self.assertEqual(len(observed), 3)
        first, second, third = [headers["x-opencode-session"] for headers in observed]
        self.assertEqual(first, second)
        self.assertNotEqual(first, third)
        self.assertNotEqual(first, "caller-spoof")
        self.assertTrue(all(headers["user-agent"] == "mastermind-go-shim/1" for headers in observed))
        original = next(row for row in self.rows("application_turns") if row["turn_id"] == "original")
        expected = "ses_mm_" + hashlib.sha256(
            b"mastermind-go-application-session/v1\0" + original["lease_id"].encode()).hexdigest()
        self.assertEqual(first, expected)
        self.assertEqual(len(self.posts), 3)
        self.assertEqual(len(self.rows("leases")), 2)


if __name__ == "__main__":
    unittest.main()
