"""Source-only Squid target/role policy invariants.

Passing this static test is not evidence that the host has Squid installed,
that a user-service BPF address filter is enforced, or that the allowed vendor
is authenticated. The workflow also runs Squid's own config parser.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[3]
CONF = ROOT / "ops" / "hermes_egress" / "squid.conf"
UNIT = ROOT / "ops" / "hermes_egress" / "hermes-egress.service"
RUNBOOK = ROOT / "ops" / "hermes_egress" / "README.md"


def _require_exact_hostname_acls(config: str) -> None:
    """Pin actual Squid syntax; this is not a substitute DNS/proxy evaluator.

    Without -n, dstdomain may turn a numeric target into a matching PTR name.
    The no-lookup flag is independently required for each exact host ACL, and
    each ACL names exactly one hostname so no host can inherit another one's
    permission.
    """
    active = [line.split("#", 1)[0].strip() for line in config.splitlines()]
    domain_acls = [line.split() for line in active
                   if line.startswith("acl ") and "dstdomain" in line.split()]
    assert domain_acls == [
        ["acl", "secretary_vendor", "dstdomain", "-n", "ark.ap-southeast.bytepluses.com"],
        ["acl", "secretary_office", "dstdomain", "-n", "mcp.mastermind-x.com"],
        ["acl", "secretary_issuer", "dstdomain", "-n", "dev-eo0jf8us5mup7wd5.us.auth0.com"],
        ["acl", "meta_vendor", "dstdomain", "-n", "api.z.ai"],
    ], "every host ACL must use exact hostname-only dstdomain -n"


class FixedRoleProxyPolicy(unittest.TestCase):
    def setUp(self):
        self.conf = CONF.read_text(encoding="utf-8")
        self.unit = UNIT.read_text(encoding="utf-8")
        self.active = [
            x.strip() for x in self.conf.splitlines()
            if x.strip() and not x.lstrip().startswith("#")
        ]
        self.rules = [x for x in self.active if x.startswith("http_access ")]

    def test_exact_two_role_loopback_listeners_only(self):
        self.assertEqual(
            [x for x in self.active if x.startswith("http_port ")],
            [
                "http_port 127.0.0.2:18651 name=hermes_secretary",
                "http_port 127.0.0.3:18652 name=hermes_meta",
            ],
        )
        self.assertNotIn("http_port 0.0.0.0", self.conf)
        self.assertNotIn("http_port [::]", self.conf)
        self.assertNotIn("intercept", "\n".join(self.active))
        self.assertNotIn("tproxy", "\n".join(self.active))

    def test_exact_two_host_port_method_pairs_and_default_deny(self):
        expected = [
            "http_access deny !CONNECT",
            "http_access deny !tls_only",
            "http_access deny forbidden_dst",
            "http_access allow secretary_socket secretary_vendor CONNECT tls_only",
            "http_access allow secretary_socket secretary_office CONNECT tls_only",
            "http_access allow secretary_socket secretary_issuer CONNECT tls_only",
            "http_access allow meta_socket meta_vendor CONNECT tls_only",
            "http_access deny all",
        ]
        self.assertEqual(self.rules, expected)
        self.assertEqual(self.active.count("acl tls_only port 443"), 1)
        self.assertEqual(self.active.count("acl secretary_vendor dstdomain -n ark.ap-southeast.bytepluses.com"), 1)
        self.assertEqual(self.active.count("acl secretary_office dstdomain -n mcp.mastermind-x.com"), 1)
        self.assertEqual(self.active.count(
            "acl secretary_issuer dstdomain -n dev-eo0jf8us5mup7wd5.us.auth0.com"), 1)
        self.assertEqual(self.active.count("acl meta_vendor dstdomain -n api.z.ai"), 1)
        self.assertEqual(self.active.count("acl secretary_socket myportname hermes_secretary"), 1)
        self.assertEqual(self.active.count("acl meta_socket myportname hermes_meta"), 1)
        self.assertFalse(any(x.startswith("http_access allow all") for x in self.active))
        self.assertFalse(any("dstdomain ." in x for x in self.active))
        self.assertFalse(any("allow localhost" in x for x in self.active))
        # Every allow line names exactly one socket ACL, one host ACL, CONNECT
        # and the 443 port; no allow line can reach a second host by accident.
        for rule in self.rules:
            if not rule.startswith("http_access allow "):
                continue
            parts = rule.split()
            self.assertEqual(parts[1], "allow")
            self.assertEqual(len(parts), 6, rule)
            self.assertTrue(parts[2].endswith("_socket"), rule)
            self.assertTrue(parts[3].endswith(("_vendor", "_office", "_issuer")), rule)
            self.assertEqual(parts[4:], ["CONNECT", "tls_only"], rule)

    def test_vendor_acls_never_fall_back_to_reverse_dns(self):
        # An IP-literal CONNECT must not become a vendor hostname through
        # attacker-controlled PTR records. Every dstdomain ACL needs -n.
        vendor_acls = [line.split() for line in self.active
                       if line.startswith("acl ") and " dstdomain " in line]
        self.assertEqual(vendor_acls, [
            ["acl", "secretary_vendor", "dstdomain", "-n", "ark.ap-southeast.bytepluses.com"],
            ["acl", "secretary_office", "dstdomain", "-n", "mcp.mastermind-x.com"],
            ["acl", "secretary_issuer", "dstdomain", "-n", "dev-eo0jf8us5mup7wd5.us.auth0.com"],
            ["acl", "meta_vendor", "dstdomain", "-n", "api.z.ai"],
        ])

    def test_stock_proxy_is_a_conflicting_ordered_unit(self):
        # Conflicts without ordering need not stop the stock proxy before
        # starting this one; both the conflict and After dependency matter.
        sections = {}
        section = None
        for raw in self.unit.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
            elif "=" in line:
                key, value = line.split("=", 1)
                sections.setdefault(section, {}).setdefault(key, []).append(value)
        unit = sections["Unit"]
        self.assertEqual(unit.get("Conflicts"), ["squid.service"])
        self.assertEqual(unit.get("After"), ["network-online.target squid.service"])
        self.assertNotIn("squid.service", " ".join(unit.get("Wants", [])))
        self.assertNotIn("squid.service", " ".join(unit.get("Requires", [])))

    def test_operator_stops_and_masks_stock_before_custom_activation(self):
        runbook = RUNBOOK.read_text(encoding="utf-8")
        blocks = re.findall(r"```sh\n(.*?)```", runbook, re.DOTALL)
        activation = [block for block in blocks
                      if "sudo systemctl enable --now hermes-egress.service" in block]
        self.assertEqual(len(activation), 1)
        commands = [line.strip() for line in activation[0].splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
        stop = "sudo systemctl disable --now squid.service && sudo systemctl mask squid.service"
        self.assertIn("set -eu", commands)
        self.assertIn(stop, commands)
        self.assertLess(commands.index(stop),
                        commands.index("sudo systemctl enable --now hermes-egress.service"))
        self.assertIn("127.0.0.1:3128", runbook)
        self.assertIn("any other non-gateway loopback listener", runbook)
        self.assertIn("PTR record", runbook)
        self.assertIn("do not stop it without its owner's authorization", runbook)

    def test_both_vendor_acls_disable_reverse_dns(self):
        _require_exact_hostname_acls(self.conf)

    def test_hostname_only_guard_rejects_each_role_lookup_or_domain_relaxation(self):
        _require_exact_hostname_acls(self.conf)
        for role, host in (
            ("secretary_vendor", "ark.ap-southeast.bytepluses.com"),
            ("secretary_office", "mcp.mastermind-x.com"),
            ("secretary_issuer", "dev-eo0jf8us5mup7wd5.us.auth0.com"),
            ("meta_vendor", "api.z.ai"),
        ):
            expected = f"acl {role} dstdomain -n {host}"
            for replacement in (
                f"acl {role} dstdomain {host}",
                f"acl {role} dstdomain -n .{host}",
                expected + " unapproved.invalid",
            ):
                with self.subTest(role=role, replacement=replacement):
                    damaged = self.conf.replace(expected, replacement, 1)
                    self.assertNotEqual(damaged, self.conf)
                    with self.assertRaises(AssertionError):
                        _require_exact_hostname_acls(damaged)

    def test_secretary_keeps_its_original_provider_and_gains_only_two_exact_hosts(self):
        # The original model vendor stays; exactly two additional exact
        # hostnames are admitted, both on the Secretary listener only.
        self.assertIn("acl secretary_vendor dstdomain -n ark.ap-southeast.bytepluses.com",
                      self.active)
        self.assertIn("acl secretary_office dstdomain -n mcp.mastermind-x.com", self.active)
        self.assertIn("acl secretary_issuer dstdomain -n dev-eo0jf8us5mup7wd5.us.auth0.com",
                      self.active)
        secretary_hosts = set()
        for rule in self.rules:
            parts = rule.split()
            if parts[0] == "http_access" and parts[1] == "allow" and parts[2] == "secretary_socket":
                secretary_hosts.add(parts[3])
        self.assertEqual(secretary_hosts, {"secretary_vendor", "secretary_office",
                                           "secretary_issuer"})
        # The Meta listener keeps its one original vendor only; its socket
        # existing is never a reason to widen it.
        meta_hosts = set()
        for rule in self.rules:
            parts = rule.split()
            if parts[0] == "http_access" and parts[1] == "allow" and parts[2] == "meta_socket":
                meta_hosts.add(parts[3])
        self.assertEqual(meta_hosts, {"meta_vendor"})
        # No cross-role allow line and no host without a socket constraint.
        for rule in self.rules:
            if not rule.startswith("http_access allow "):
                continue
            parts = rule.split()
            self.assertEqual(sum([parts[2].endswith("_socket"), parts[3].endswith("_socket")]),
                             1, rule)
            # The socket ACL and the host ACL belong to the same role.
            self.assertEqual(parts[2].split("_")[0], parts[3].split("_")[0], rule)

    def test_no_wildcard_suffix_or_direct_address_reach_in_the_host_acls(self):
        # No leading dot (subdomain suffix), no wildcard, no bare IP, no
        # reverse-DNS fallback and no second host inside one ACL.
        for line in self.active:
            if not line.startswith("acl ") or " dstdomain " not in line:
                continue
            parts = line.split()
            self.assertEqual(len(parts), 5, line)
            self.assertEqual(parts[3], "-n", line)
            host = parts[4]
            self.assertNotIn("*", host, line)
            self.assertNotIn(".", host[0], line)
            self.assertNotRegex(host, r"^\d+\.\d+\.\d+\.\d+$")
            self.assertIn(".", host, line)
        # No address-literal host permission and no direct-IP expansion.
        self.assertFalse(any(re.search(r"dstdomain\s+\d+\.\d+\.\d+\.\d+", x)
                             for x in self.active))
        self.assertFalse(any("dns" in x.split() and x.split()[0] == "dns" for x in self.active))
        self.assertNotIn("url_regex", " ".join(self.active))
        # Only the explicit forbidden-range ACL may use the bare address type;
        # no host ACL may be expressed as a resolved address instead of a name.
        for line in self.active:
            if not line.startswith("acl ") or " dstdomain " in line:
                continue
            parts = line.split()
            if parts[1] == "forbidden_dst":
                continue
            self.assertNotIn("dst", parts[2:], line)

    def test_internal_destinations_rejected_before_either_allow(self):
        forbidden = next(x for x in self.active if x.startswith("acl forbidden_dst dst "))
        for expected in (
            "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10",
            "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
            "192.168.0.0/16", "198.18.0.0/15",
            "224.0.0.0/4", "240.0.0.0/4",
            "::/128", "::1/128", "fc00::/7", "fe80::/10",
        ):
            with self.subTest(cidr=expected):
                self.assertIn(expected, forbidden)
        deny = self.rules.index("http_access deny forbidden_dst")
        # The private/loopback deny precedes EVERY allow, including the two
        # new exact-host allows; otherwise a rebinding or misconfigured DNS
        # answer could reach an allowed hostname through a forbidden address.
        for index, rule in enumerate(self.rules):
            if rule.startswith("http_access allow "):
                with self.subTest(rule=rule):
                    self.assertLess(deny, index)
        self.assertEqual(self.rules[-1], "http_access deny all")
        self.assertEqual(self.rules.index("http_access deny !CONNECT"), 0)
        self.assertEqual(self.rules.index("http_access deny !tls_only"), 1)

    def test_no_tls_interception_caching_or_proxy_secret_material(self):
        self.assertIn("cache deny all", self.active)
        self.assertIn("cache_store_log none", self.active)
        self.assertFalse(any(x.startswith((
            "ssl_bump", "https_port", "cache_peer", "cache_dir", "tls_outgoing_options",
            "sslproxy_cert_error", "request_header_add",
        )) for x in self.active))
        self.assertNotRegex(self.conf, r"(?im)^(?:authorization|api[_-]?key|password|token)\s*[:=]")
        self.assertNotRegex(self.unit, r"(?im)^(?:environment|environmentfile)=")

    def test_one_existing_distro_squid_binary_not_two_new_control_planes(self):
        lines = [l.strip() for l in self.unit.splitlines()
                 if l.strip() and not l.strip().startswith("#")]
        self.assertIn("Type=simple", lines)
        self.assertIn("User=proxy", lines)
        self.assertIn("NoNewPrivileges=yes", lines)
        self.assertIn("ProtectSystem=strict", lines)
        self.assertIn("PrivateDevices=yes", lines)
        self.assertIn("ExecStartPre=/usr/sbin/squid -k parse -f /etc/squid/hermes-byok.conf", lines)
        self.assertIn("ExecStart=/usr/sbin/squid -N -f /etc/squid/hermes-byok.conf", lines)
        self.assertEqual(len([x for x in lines if x.startswith("ExecStart=")]), 1)
        self.assertEqual(len([x for x in lines if x.startswith("ExecStartPre=")]), 1)
        self.assertEqual(len([x for x in lines if x.startswith("User=")]), 1)
        self.assertNotIn("IPAddressAllow=any", self.unit)


class DamagedPolicyIsRefused(unittest.TestCase):
    """Each guard must actually discriminate, not merely accept the good file."""

    def setUp(self):
        self.conf = CONF.read_text(encoding="utf-8")

    @staticmethod
    def _active(config):
        return [x.strip() for x in config.splitlines()
                if x.strip() and not x.lstrip().startswith("#")]

    @classmethod
    def _rules(cls, config):
        return [x for x in cls._active(config) if x.startswith("http_access ")]

    @staticmethod
    def _guard_acl_shape(config):
        _require_exact_hostname_acls(config)
        for line in DamagedPolicyIsRefused._active(config):
            if not line.startswith("acl ") or " dstdomain " not in line:
                continue
            parts = line.split()
            assert len(parts) == 5, line
            assert parts[3] == "-n", line
            assert "*" not in parts[4], line
            assert not parts[4].startswith("."), line

    @staticmethod
    def _guard_allow_shape(config):
        for rule in DamagedPolicyIsRefused._rules(config):
            if not rule.startswith("http_access allow "):
                continue
            parts = rule.split()
            assert len(parts) == 6, rule
            assert sum([parts[2].endswith("_socket"), parts[3].endswith("_socket")]) == 1, rule
            assert parts[2].split("_")[0] == parts[3].split("_")[0], rule
            assert parts[4:] == ["CONNECT", "tls_only"], rule

    @staticmethod
    def _guard_deny_order(config):
        rules = DamagedPolicyIsRefused._rules(config)
        deny = rules.index("http_access deny forbidden_dst")
        for index, rule in enumerate(rules):
            if rule.startswith("http_access allow "):
                assert deny < index, rule

    @staticmethod
    def _guard_default_deny(config):
        assert DamagedPolicyIsRefused._rules(config)[-1] == "http_access deny all"

    def test_the_undamaged_policy_satisfies_every_guard(self):
        for guard in (self._guard_acl_shape, self._guard_allow_shape,
                      self._guard_deny_order, self._guard_default_deny):
            with self.subTest(guard=guard.__name__):
                guard(self.conf)

    def test_every_damage_is_refused_by_the_matching_guard(self):
        damages = {
            # The new exact hosts lose their no-lookup flag.
            "office-no-lookup": (
                "acl secretary_office dstdomain -n mcp.mastermind-x.com",
                "acl secretary_office dstdomain mcp.mastermind-x.com", "_guard_acl_shape"),
            "issuer-no-lookup": (
                "acl secretary_issuer dstdomain -n dev-eo0jf8us5mup7wd5.us.auth0.com",
                "acl secretary_issuer dstdomain dev-eo0jf8us5mup7wd5.us.auth0.com",
                "_guard_acl_shape"),
            # A leading dot turns the exact host into a suffix permission.
            "office-suffix": (
                "acl secretary_office dstdomain -n mcp.mastermind-x.com",
                "acl secretary_office dstdomain -n .mcp.mastermind-x.com", "_guard_acl_shape"),
            "issuer-suffix": (
                "acl secretary_issuer dstdomain -n dev-eo0jf8us5mup7wd5.us.auth0.com",
                "acl secretary_issuer dstdomain -n .dev-eo0jf8us5mup7wd5.us.auth0.com",
                "_guard_acl_shape"),
            # A wildcard host is not an exact host.
            "office-wildcard": (
                "acl secretary_office dstdomain -n mcp.mastermind-x.com",
                "acl secretary_office dstdomain -n *.mastermind-x.com", "_guard_acl_shape"),
            # The Meta role must not inherit the Secretary's new hosts.
            "meta-inherits-office": (
                "http_access allow meta_socket meta_vendor CONNECT tls_only",
                "http_access allow meta_socket meta_vendor secretary_office CONNECT tls_only",
                "_guard_allow_shape"),
            # The Secretary must not inherit the Meta vendor.
            "secretary-inherits-meta": (
                "http_access allow secretary_socket secretary_vendor CONNECT tls_only",
                "http_access allow secretary_socket secretary_vendor meta_vendor CONNECT tls_only",
                "_guard_allow_shape"),
            # The office host must not be reachable on any port.
            "office-any-port": (
                "http_access allow secretary_socket secretary_office CONNECT tls_only",
                "http_access allow secretary_socket secretary_office CONNECT",
                "_guard_allow_shape"),
            # The forbidden-range deny must precede every allow.
            "allow-before-deny": (
                "http_access deny forbidden_dst",
                "http_access allow secretary_socket secretary_office CONNECT tls_only\n"
                "http_access deny forbidden_dst", "_guard_deny_order"),
            # The final default deny is the whole fail-closed boundary.
            "no-default-deny": ("http_access deny all", "http_access allow all",
                                "_guard_default_deny"),
        }
        guards = {"_guard_acl_shape": self._guard_acl_shape,
                  "_guard_allow_shape": self._guard_allow_shape,
                  "_guard_deny_order": self._guard_deny_order,
                  "_guard_default_deny": self._guard_default_deny}
        for name, (before, after, guard) in damages.items():
            with self.subTest(damage=name):
                damaged = self.conf.replace(before, after, 1)
                self.assertNotEqual(damaged, self.conf)
                with self.assertRaises(AssertionError):
                    guards[guard](damaged)


if __name__ == "__main__":
    unittest.main()
