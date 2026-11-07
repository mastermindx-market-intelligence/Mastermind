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
    The no-lookup flag is independently required for each exact vendor ACL.
    """
    active = [line.split("#", 1)[0].strip() for line in config.splitlines()]
    domain_acls = [line.split() for line in active
                   if line.startswith("acl ") and "dstdomain" in line.split()]
    assert domain_acls == [
        ["acl", "secretary_vendor", "dstdomain", "-n", "ark.ap-southeast.bytepluses.com"],
        ["acl", "meta_vendor", "dstdomain", "-n", "api.z.ai"],
    ], "both vendor ACLs must use exact hostname-only dstdomain -n"


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
            "http_access allow meta_socket meta_vendor CONNECT tls_only",
            "http_access deny all",
        ]
        self.assertEqual(self.rules, expected)
        self.assertEqual(self.active.count("acl tls_only port 443"), 1)
        self.assertEqual(self.active.count("acl secretary_vendor dstdomain -n ark.ap-southeast.bytepluses.com"), 1)
        self.assertEqual(self.active.count("acl meta_vendor dstdomain -n api.z.ai"), 1)
        self.assertEqual(self.active.count("acl secretary_socket myportname hermes_secretary"), 1)
        self.assertEqual(self.active.count("acl meta_socket myportname hermes_meta"), 1)
        self.assertFalse(any(x.startswith("http_access allow all") for x in self.active))
        self.assertFalse(any("dstdomain ." in x for x in self.active))
        self.assertFalse(any("allow localhost" in x for x in self.active))

    def test_vendor_acls_never_fall_back_to_reverse_dns(self):
        # An IP-literal CONNECT must not become a vendor hostname through
        # attacker-controlled PTR records. Every dstdomain ACL needs -n.
        vendor_acls = [line.split() for line in self.active
                       if line.startswith("acl ") and " dstdomain " in line]
        self.assertEqual(vendor_acls, [
            ["acl", "secretary_vendor", "dstdomain", "-n", "ark.ap-southeast.bytepluses.com"],
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
        self.assertLess(self.rules.index("http_access deny forbidden_dst"),
                        self.rules.index("http_access allow secretary_socket secretary_vendor CONNECT tls_only"))
        self.assertLess(self.rules.index("http_access deny forbidden_dst"),
                        self.rules.index("http_access allow meta_socket meta_vendor CONNECT tls_only"))

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


if __name__ == "__main__":
    unittest.main()
