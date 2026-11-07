"""Measured Linux MemTotal -> granular.mem_total_bytes (proposal evidence).

Executes the repository's own probe program and adapter mapping from
$MEMTOTAL_ROOT (default: quota_continuity tree beside this file). Only the
probe program's input roots are re-pointed, at run time, at a disposable fake
tree (/proc, /sys); the rest are the shipped bytes. No host, SSH or network.

  MEMTOTAL_ROOT=<tree> python3 -m unittest test_host_mem_total_telemetry -v
"""
import math, os, pathlib, re, subprocess, sys, tempfile, textwrap, unittest

ROOT = pathlib.Path(os.environ.get("MEMTOTAL_ROOT") or pathlib.Path(__file__).resolve().parents[1])
TREE = ("candidate",)
FILES = {n: (ROOT / n / "host_pull_probe.template",
              ROOT / n / "host_pull_backend.py") for n in TREE}
KIB = 1024
TOTAL, AVAILABLE, SWAP = 16384000 * KIB, 8192000 * KIB, (2097152 - 1048576) * KIB
AVAIL_LINE = "MemAvailable:    8192000 kB\n"
FULL = ("MemTotal:       16384000 kB\n" + AVAIL_LINE +
        "SwapTotal:       2097152 kB\nSwapFree:        1048576 kB\n")
NO_TOTAL = AVAIL_LINE + "SwapTotal:       2097152 kB\nSwapFree:        1048576 kB\n"
BAD_TOTAL = "MemTotal:       not-a-number kB\n" + AVAIL_LINE
ZERO_TOTAL = "MemTotal:       0 kB\n" + AVAIL_LINE
# probe input roots; exact counts stop a template edit redirecting the fixture
ROOTS = (('pathlib.Path("/sys/class/hwmon")', "sys/class/hwmon", 1),
         ('pathlib.Path("/sys/devices/system/cpu")', "sys/devices/system/cpu", 1),
         ('pathlib.Path("/proc/pressure")', "proc/pressure", 1),
         ('pathlib.Path("/proc")', "proc", 3))
BAD = (True, False, 123, 1.5, None, "0", "-1", "-16777216000", "", " 1", "1.5",
       "1e10", "0x10", "١٢", "1" * 21)


def probe(template, meminfo):
    text = template.read_text(encoding="utf-8")
    program = text[text.index("    thermals=$(python3 -c '") + len("    thermals=$(python3 -c '"):
                   text.index("' 2>/dev/null) || thermals=\"\"")]
    with tempfile.TemporaryDirectory() as tmp:
        fake = pathlib.Path(tmp)
        for d in ("proc/pressure", "sys/class/hwmon", "sys/devices/system/cpu"):
            (fake / d).mkdir(parents=True)
        (fake / "proc" / "meminfo").write_text(meminfo, encoding="ascii")
        (fake / "proc" / "stat").write_text("", encoding="ascii")
        for literal, relative, expected in ROOTS:
            assert program.count(literal) == expected, literal
            program = program.replace(literal, "pathlib.Path(%r)" % str(fake / relative))
        result = subprocess.run([sys.executable, "-c", program], text=True,
                                capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return result.stdout


def granular(text, kv):
    lines = text.splitlines(keepends=True)
    start = next(i for i, l in enumerate(lines)
                 if l.strip() == "def safe_float(name, low=0.0, high=100.0):")
    assign = next(i for i, l in enumerate(lines) if l.strip().startswith('doc["granular"]={'))
    depth, end = 0, None
    for i in range(assign, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth == 0:
            end = i
            break
    assert end is not None
    doc = {"host": "fixture-host", "ts": 1700000000}
    ns = {"kv": kv, "doc": doc, "math": math, "re": re}
    exec(compile(textwrap.dedent("".join(lines[start:end + 1])), "<granular>", "exec"), ns)
    return doc["granular"]


class MemTotalTelemetry(unittest.TestCase):
    def test_measured_total_is_reported_by_probe_and_adapter(self):
        for n in TREE:
            with self.subTest(tree=n):
                tpl, be = FILES[n]
                out = probe(tpl, FULL).splitlines()
                self.assertIn("therm_mem_total_bytes=%d" % TOTAL, out)
                self.assertIn("therm_mem_available_bytes=%d" % AVAILABLE, out)
                self.assertIn("therm_swap_used_bytes=%d" % SWAP, out)
                self.assertIn("therm_reader=hwmon_v1", out)
                text = be.read_text(encoding="utf-8")
                g = granular(text, {"therm_reader": "hwmon_v1",
                                    "therm_mem_available_bytes": str(AVAILABLE),
                                    "therm_mem_total_bytes": str(TOTAL),
                                    "therm_swap_used_bytes": str(SWAP)})
                self.assertEqual(g.get("mem_total_bytes"), TOTAL)
                self.assertEqual(g.get("mem_available_bytes"), AVAILABLE)
                self.assertEqual(g.get("swap_used_bytes"), SWAP)
                # shape and admission authority are untouched
                self.assertEqual(g.get("schema"), "mastermind.fabric_host_granular.v1")
                self.assertEqual(g.get("source"), "linux_procfs")
                self.assertIs(g.get("admission_authoritative"), False)
                for key in ("observed_at", "cpu_busy_pct"):
                    self.assertIn(key, g)

    def test_unmeasured_total_is_unknown_and_never_inferred(self):
        for case, meminfo in (("absent", NO_TOTAL), ("malformed", BAD_TOTAL),
                              ("zero", ZERO_TOTAL)):
            for n in TREE:
                with self.subTest(case=case, tree=n):
                    tpl, be = FILES[n]
                    out = probe(tpl, meminfo)
                    self.assertNotIn("therm_mem_total_bytes", out)
                    text = be.read_text(encoding="utf-8")
                    g = granular(text, {"therm_reader": "hwmon_v1",
                                        "therm_mem_available_bytes": str(AVAILABLE)})
                    self.assertIsNone(g.get("mem_total_bytes"))
                    # available is still measured, never promoted to total
                    self.assertEqual(g.get("mem_available_bytes"), AVAILABLE)

    def test_adapter_rejects_boolean_non_string_and_negative(self):
        for n in TREE:
            with self.subTest(tree=n):
                text = FILES[n][1].read_text(encoding="utf-8")
                for bad in BAD:
                    kv = {"therm_reader": "hwmon_v1",
                          "therm_mem_available_bytes": str(AVAILABLE),
                          "therm_mem_total_bytes": bad}
                    self.assertIsNone(granular(text, kv).get("mem_total_bytes"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
