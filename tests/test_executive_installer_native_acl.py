#!/usr/bin/env python3
"""Inert unittest harness for native_acl.rb.

Executes the ACTUAL returned Ruby source: each case generates a small Ruby
wrapper that `load`s native_acl.rb (so the real classes, the real probe logic
and the real main-guard are exercised) and injects fake collaborators
(lstat / native ACL resolver / directory-entry provider). The harness never
performs a real ACL call, never mutates a filesystem, and never runs external
commands from Ruby. All assertion evidence comes from recorded fake-collaborator
traces returned over stdout.

When no Ruby interpreter is installed, every test class skips with an explicit
reason. (This host, at authoring time, has no Ruby: see NOTES.md.)
"""

import os
import pwd
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALLER = os.path.join(HERE, "..", "ops", "executive_os", "install.sh")


def reader_source():
    with open(INSTALLER, encoding="utf-8") as stream:
        text = stream.read()
    return text.split("<<'MASTERMIND_NATIVE_ACL_RUBY'\n", 1)[1].split("\nMASTERMIND_NATIVE_ACL_RUBY\n", 1)[0] + "\n"


def write_reader(tmpdir):
    path = os.path.join(tmpdir, "native_acl.rb")
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(reader_source())
    return path
RUBY = shutil.which("ruby")
SKIP_REASON = (
    "ruby interpreter not available on this host; "
    "inert Ruby-logic cases skipped (no real ACL calls anywhere regardless)"
)

WRAPPER_TEMPLATE = r"""# AUTO-GENERATED inert test wrapper for native_acl.rb.
# Loads the real artifact and injects fake collaborators only.
ARTIFACT_PATH = ARGV.fetch(0)
load ARTIFACT_PATH

FakeStat = Struct.new(:dev, :ino, :mode, :uid, :gid, :nlink, :size,
                      :mtime, :ctime, :atime, :kind) do
  def file?; kind == :file; end
  def directory?; kind == :dir; end
  def symlink?; kind == :symlink; end
end

def fstat(kind: :file, **over)
  base = { dev: 1, ino: 1, mode: 33188, uid: 501, gid: 20, nlink: 1,
           size: 10, mtime: 1_700_000_000, ctime: 1_700_000_000,
           atime: 1_699_999_999 }
  h = base.merge(over)
  FakeStat.new(h[:dev], h[:ino], h[:mode], h[:uid], h[:gid], h[:nlink],
               h[:size], h[:mtime], h[:ctime], h[:atime], kind)
end

class FakeLstat
  attr_reader :paths
  attr_accessor :table

  def initialize(table = {})
    @table = table
    @paths = []
  end

  def lstat(path)
    @paths << path
    e = @table.fetch(path) { raise "unexpected lstat #{path}" }
    e = (e.size > 1 ? e.shift : e.first) if e.is_a?(Array)
    raise NativeAcl::Refusal, :missing if e == :missing
    raise NativeAcl::Refusal, :lstat_error if e == :lstat_error
    raise NativeAcl::Refusal, :lstat_error if e == :enotdir
    e
  end
end

class FakePointer
  def initialize(null); @null = null; end
  def null?; @null; end
end

class FakeResolver
  attr_reader :gets, :frees, :freed
  attr_accessor :behavior

  def initialize(behavior = :absent)
    @behavior = behavior
    @gets = []
    @frees = 0
    @freed = []
  end

  # Mirrors the real NativeResolver contract: :absent only for NULL+ENOENT,
  # an allocated (null? == false) pointer for ANY present ACL, Refusal for
  # every other NULL errno or an unavailable native API.
  def get_link(path)
    @gets << path
    case @behavior
    when :absent                          then :absent
    when :present, :empty_acl, :free_fail, :free_throw
      FakePointer.new(false)
    when :null_eacces, :null_eio, :null_einval
      raise NativeAcl::Refusal, :acl_error
    when :unavailable
      raise NativeAcl::Refusal, :runtime
    else
      raise "unknown behavior #{@behavior}"
    end
  end

  def acl_free(ptr)
    @frees += 1
    @freed << ptr
    raise "acl_free threw" if @behavior == :free_throw
    return 1 if @behavior == :free_fail
    0
  end
end

class FakeEntries
  attr_accessor :table

  def initialize(table = {}); @table = table; end

  def children(dir)
    v = @table.fetch(dir, [])
    raise NativeAcl::Refusal, :traverse_error if v == :error
    v.sort
  end
end

$cases = []

def emit(name)
  lstat = FakeLstat.new
  resolver = FakeResolver.new
  entries = FakeEntries.new
  cfg = yield lstat, resolver, entries
  runner = NativeAcl::Runner.new(lstat: lstat, resolver: resolver,
                                 entries: entries)
  code = runner.run([cfg[:mode]] + cfg[:paths])
  $cases << { "name" => name, "exit" => code,
              "reason" => runner.last_reason ? runner.last_reason.to_s : "-",
              "gets" => resolver.gets.join("|"),
              "lstats" => lstat.paths.join("|"),
              "frees" => resolver.frees.to_s }
rescue StandardError => e
  $cases << { "name" => name, "error" => "#{e.class}: #{e.message}" }
end

def emit_parse(name, argv)
  begin
    NativeAcl::PathPolicy.parse(argv)
    $cases << { "name" => name, "ok" => "true", "reason" => "-" }
  rescue NativeAcl::Refusal => e
    $cases << { "name" => name, "ok" => "false", "reason" => e.reason.to_s }
  rescue StandardError => e
    $cases << { "name" => name, "error" => "#{e.class}: #{e.message}" }
  end
end

def emit_identity(name, a, b)
  begin
    r = NativeAcl::Identity.same?(a, b)
    $cases << { "name" => name, "ok" => r ? "true" : "false", "reason" => "-" }
  rescue StandardError => e
    $cases << { "name" => name, "error" => "#{e.class}: #{e.message}" }
  end
end

# ---- scenario definitions (inserted per group) ----
__SCENARIOS__

$cases.each do |c|
  puts "CASE #{c['name']}"
  if c.key?("error")
    puts "ERROR #{c['error']}"
  elsif c.key?("ok")
    puts "OK #{c['ok']}"
    puts "REASON #{c['reason']}"
  else
    puts "EXIT #{c['exit']}"
    puts "REASON #{c['reason']}"
    puts "GETS #{c['gets']}"
    puts "LSTATS #{c['lstats']}"
    puts "FREES #{c['frees']}"
  end
  puts "ENDCASE"
end
"""


def parse_cases(out):
    cases = {}
    cur = None
    for line in out.splitlines():
        if line.startswith("CASE "):
            cur = line[5:].strip()
            cases[cur] = {}
        elif line == "ENDCASE":
            cur = None
        elif cur is not None and " " in line:
            key, val = line.split(" ", 1)
            cases[cur][key] = val
    return cases


def run_ruby_wrapper(scenarios, tmpdir):
    wrapper = os.path.join(tmpdir, "wrap.rb")
    with open(wrapper, "w", encoding="utf-8") as fh:
        fh.write(WRAPPER_TEMPLATE.replace("__SCENARIOS__", scenarios))
    proc = subprocess.run(
        [RUBY, "--disable-gems", "--disable=rubyopt", wrapper, write_reader(tmpdir)],
        capture_output=True, text=True, timeout=20,
    )
    if proc.returncode != 0:
        raise AssertionError(
            "wrapper exited %s\nstderr:\n%s\nstdout:\n%s"
            % (proc.returncode, proc.stderr, proc.stdout)
        )
    return parse_cases(proc.stdout)


class GroupTest(unittest.TestCase):
    """Base: runs one scenario group once and shares parsed cases."""

    GROUP = ""

    @classmethod
    def setUpClass(cls):
        if not RUBY:
            raise unittest.SkipTest(SKIP_REASON)
        cls.tmp = tempfile.TemporaryDirectory(prefix="native_acl_ut_")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.cases = run_ruby_wrapper(cls.GROUP, cls.tmp.name)

    def case(self, name):
        self.assertIn(name, self.cases, "case %s missing" % name)
        c = self.cases[name]
        self.assertNotIn(
            "ERROR", c, "ruby-level failure in %s: %s" % (name, c.get("ERROR"))
        )
        return c

    def assert_ok(self, name, gets=None, lstats=None):
        c = self.case(name)
        self.assertEqual(c["EXIT"], "0", name)
        self.assertEqual(c["REASON"], "-", name)
        self.assertEqual(c["FREES"], "0", name)
        if gets is not None:
            self.assertEqual(c["GETS"], gets, name)
        if lstats is not None:
            self.assertEqual(c["LSTATS"], lstats, name)
        return c

    def assert_refused(self, name, reason, frees=None):
        c = self.case(name)
        self.assertEqual(c["EXIT"], "65", name)
        self.assertEqual(c["REASON"], reason, name)
        if frees is not None:
            self.assertEqual(c["FREES"], frees, name)
        return c


def run_cli(argv):
    source = reader_source()
    return subprocess.run(
        [RUBY, "--disable-gems", "--disable=rubyopt", "-"] + list(argv),
        input=source, capture_output=True, text=True, timeout=20,
    )

GROUP_ONE = r"""
emit("absent_file") do |lstat, _resolver, _entries|
  lstat.table["/f"] = fstat
  { mode: "one", paths: ["/f"] }
end

emit("absent_dir") do |lstat, _resolver, _entries|
  lstat.table["/d"] = fstat(kind: :dir, ino: 7)
  { mode: "one", paths: ["/d"] }
end

emit("absent_symlink_nofollow") do |lstat, _resolver, _entries|
  # Only the link object is in the table; any lstat of a target path would
  # raise "unexpected lstat" and fail the case. Native query must hit the
  # link path itself, never "/real/target".
  lstat.table["/link"] = fstat(kind: :symlink, ino: 9)
  { mode: "one", paths: ["/link"] }
end

emit("absent_two_paths") do |lstat, resolver, _entries|
  lstat.table["/a"] = fstat(ino: 1)
  lstat.table["/b"] = fstat(ino: 2)
  { mode: "one", paths: ["/a", "/b"] }
end

emit("atime_change_only_ok") do |lstat, _resolver, _entries|
  # atime is excluded from the identity tuple by contract.
  lstat.table["/f"] = [fstat(atime: 1_699_999_999), fstat(atime: 1_800_000_000)]
  { mode: "one", paths: ["/f"] }
end

emit("missing_before") do |lstat, resolver, _entries|
  lstat.table["/gone"] = :missing
  { mode: "one", paths: ["/gone"] }
end

emit("missing_after") do |lstat, _resolver, _entries|
  # Missing after is not ACL absence: must refuse.
  lstat.table["/f"] = [fstat, :missing]
  { mode: "one", paths: ["/f"] }
end

emit("lstat_eacces_before") do |lstat, _resolver, _entries|
  lstat.table["/f"] = :lstat_error
  { mode: "one", paths: ["/f"] }
end

emit("lstat_enotdir") do |lstat, _resolver, _entries|
  lstat.table["/f/etc"] = :enotdir
  { mode: "one", paths: ["/f/etc"] }
end

emit("fifo_refused") do |lstat, _resolver, _entries|
  s = fstat
  s.kind = :fifo
  lstat.table["/pipe"] = s
  { mode: "one", paths: ["/pipe"] }
end
"""

GROUP_ACL = r"""
emit("acl_absent_ok") do |lstat, _resolver, _entries|
  lstat.table["/f"] = fstat
  { mode: "one", paths: ["/f"] }
end

emit("acl_present_refused") do |lstat, resolver, _entries|
  lstat.table["/f"] = fstat
  resolver.behavior = :present
  { mode: "one", paths: ["/f"] }
end

emit("acl_empty_allocated_refused") do |lstat, resolver, _entries|
  # An allocated but empty ACL still refuses.
  lstat.table["/f"] = fstat
  resolver.behavior = :empty_acl
  { mode: "one", paths: ["/f"] }
end

emit("acl_null_eacces") do |lstat, resolver, _entries|
  lstat.table["/f"] = fstat
  resolver.behavior = :null_eacces
  { mode: "one", paths: ["/f"] }
end

emit("acl_null_eio") do |lstat, resolver, _entries|
  lstat.table["/f"] = fstat
  resolver.behavior = :null_eio
  { mode: "one", paths: ["/f"] }
end

emit("acl_null_einval") do |lstat, resolver, _entries|
  lstat.table["/f"] = fstat
  resolver.behavior = :null_einval
  { mode: "one", paths: ["/f"] }
end

emit("acl_api_unavailable") do |lstat, resolver, _entries|
  lstat.table["/f"] = fstat
  resolver.behavior = :unavailable
  { mode: "one", paths: ["/f"] }
end

emit("acl_free_fails") do |lstat, resolver, _entries|
  lstat.table["/f"] = fstat
  resolver.behavior = :free_fail
  { mode: "one", paths: ["/f"] }
end

emit("acl_free_throws") do |lstat, resolver, _entries|
  lstat.table["/f"] = fstat
  resolver.behavior = :free_throw
  { mode: "one", paths: ["/f"] }
end

emit("identity_drift_size") do |lstat, _resolver, _entries|
  lstat.table["/f"] = [fstat(size: 10), fstat(size: 11)]
  { mode: "one", paths: ["/f"] }
end

emit("identity_drift_mtime") do |lstat, _resolver, _entries|
  lstat.table["/f"] = [fstat(mtime: 1), fstat(mtime: 2)]
  { mode: "one", paths: ["/f"] }
end

emit("identity_drift_ino") do |lstat, _resolver, _entries|
  lstat.table["/f"] = [fstat(ino: 1), fstat(ino: 2)]
  { mode: "one", paths: ["/f"] }
end
"""

GROUP_TREE = r"""
emit("tree_absent_ok") do |lstat, _resolver, entries|
  lstat.table["/t"] = fstat(kind: :dir, ino: 10)
  lstat.table["/t/file"] = fstat(ino: 12)
  lstat.table["/t/link"] = fstat(kind: :symlink, ino: 13)
  lstat.table["/t/sub"] = fstat(kind: :dir, ino: 11)
  lstat.table["/t/sub/deep"] = fstat(ino: 14)
  entries.table["/t"] = ["file", "link", "sub"]
  entries.table["/t/sub"] = ["deep"]
  entries.table["/t/sub/deep"] = []
  { mode: "tree", paths: ["/t"] }
end

emit("tree_acl_present_deep") do |lstat, resolver, entries|
  lstat.table["/t"] = fstat(kind: :dir, ino: 10)
  lstat.table["/t/sub"] = fstat(kind: :dir, ino: 11)
  lstat.table["/t/sub/deep"] = fstat(ino: 14)
  entries.table["/t"] = ["sub"]
  entries.table["/t/sub"] = ["deep"]
  entries.table["/t/sub/deep"] = []
  resolver.behavior = :present
  { mode: "tree", paths: ["/t"] }
end

emit("tree_dir_identity_changed") do |lstat, _resolver, entries|
  # Enumerated directory replaced after traversal: before/after mismatch.
  lstat.table["/t"] = [fstat(kind: :dir, ino: 10), fstat(kind: :dir, ino: 99)]
  lstat.table["/t/a"] = fstat(ino: 12)
  entries.table["/t"] = ["a"]
  { mode: "tree", paths: ["/t"] }
end

emit("tree_child_replaced") do |lstat, _resolver, entries|
  # Entry replaced between its before-lstat and after-lstat.
  lstat.table["/t"] = fstat(kind: :dir, ino: 10)
  lstat.table["/t/a"] = [fstat(ino: 12), fstat(ino: 77)]
  entries.table["/t"] = ["a"]
  { mode: "tree", paths: ["/t"] }
end

emit("tree_entry_vanished") do |lstat, _resolver, entries|
  # Unknown/vanished entries refuse; they are never silently skipped.
  lstat.table["/t"] = fstat(kind: :dir, ino: 10)
  lstat.table["/t/a"] = :missing
  entries.table["/t"] = ["a"]
  { mode: "tree", paths: ["/t"] }
end

emit("tree_fifo_entry") do |lstat, _resolver, entries|
  lstat.table["/t"] = fstat(kind: :dir, ino: 10)
  s = fstat
  s.kind = :fifo
  lstat.table["/t/p"] = s
  entries.table["/t"] = ["p"]
  { mode: "tree", paths: ["/t"] }
end

emit("tree_root_not_dir") do |lstat, _resolver, _entries|
  lstat.table["/f"] = fstat(ino: 5)
  { mode: "tree", paths: ["/f"] }
end

emit("tree_root_symlink") do |lstat, _resolver, _entries|
  lstat.table["/s"] = fstat(kind: :symlink, ino: 6)
  { mode: "tree", paths: ["/s"] }
end

emit("tree_traverse_error") do |lstat, _resolver, entries|
  lstat.table["/t"] = fstat(kind: :dir, ino: 10)
  entries.table["/t"] = :error
  { mode: "tree", paths: ["/t"] }
end
"""

GROUP_PURE = r"""
emit_parse("policy_ok_one", ["one", "/x"])
emit_parse("policy_ok_tree", ["tree", "/x", "/y"])
emit_parse("policy_unknown_mode", ["all", "/x"])
emit_parse("policy_no_mode", [])
emit_parse("policy_no_paths", ["one"])
emit_parse("policy_relative", ["one", "rel/path"])
emit_parse("policy_nul_in_path", ["one", "a\0b"])
emit_parse("policy_nul_in_mode", ["on\0e", "/x"])

emit_identity("identity_same", fstat, fstat)
emit_identity("identity_uid_diff", fstat, fstat(uid: 0))
emit_identity("identity_ctime_diff", fstat, fstat(ctime: 123))
emit_identity("identity_nlink_diff", fstat, fstat(nlink: 2))
"""


@unittest.skipUnless(RUBY, SKIP_REASON)
class TestOneMode(GroupTest):
    GROUP = GROUP_ONE

    def test_absent_file_ok(self):
        self.assert_ok("absent_file", gets="/f", lstats="/f|/f")

    def test_absent_dir_ok(self):
        self.assert_ok("absent_dir", gets="/d", lstats="/d|/d")

    def test_symlink_inspected_not_followed(self):
        c = self.assert_ok("absent_symlink_nofollow", gets="/link")
        self.assertEqual(c["LSTATS"], "/link|/link")
        self.assertNotIn("/real/target", c["GETS"])
        self.assertNotIn("/real/target", c["LSTATS"])

    def test_two_paths_both_inspected(self):
        self.assert_ok("absent_two_paths", gets="/a|/b")

    def test_atime_excluded_from_identity(self):
        self.assert_ok("atime_change_only_ok", gets="/f")

    def test_missing_before_refuses_without_native_query(self):
        c = self.assert_refused("missing_before", "missing")
        self.assertEqual(c["GETS"], "")

    def test_missing_after_refuses(self):
        self.assert_refused("missing_after", "missing")

    def test_lstat_eacces_refuses(self):
        self.assert_refused("lstat_eacces_before", "lstat_error")

    def test_lstat_enotdir_refuses(self):
        self.assert_refused("lstat_enotdir", "lstat_error")

    def test_unsupported_type_refuses(self):
        self.assert_refused("fifo_refused", "unsupported")


@unittest.skipUnless(RUBY, SKIP_REASON)
class TestAclProbe(GroupTest):
    GROUP = GROUP_ACL

    def test_absent_ok(self):
        self.assert_ok("acl_absent_ok", gets="/f")

    def test_present_refuses_and_freed_exactly_once(self):
        self.assert_refused("acl_present_refused", "acl_present", frees="1")

    def test_empty_allocated_acl_refuses_and_freed_exactly_once(self):
        self.assert_refused(
            "acl_empty_allocated_refused", "acl_present", frees="1"
        )

    def test_null_eacces_refuses(self):
        self.assert_refused("acl_null_eacces", "acl_error")

    def test_null_eio_refuses(self):
        self.assert_refused("acl_null_eio", "acl_error")

    def test_null_other_errno_refuses(self):
        self.assert_refused("acl_null_einval", "acl_error")

    def test_unavailable_api_refuses(self):
        self.assert_refused("acl_api_unavailable", "runtime")

    def test_free_failure_refuses_without_retry(self):
        self.assert_refused("acl_free_fails", "acl_free_error", frees="1")

    def test_free_throw_refuses_without_retry(self):
        self.assert_refused("acl_free_throws", "acl_free_error", frees="1")

    def test_identity_drift_size(self):
        self.assert_refused("identity_drift_size", "identity", frees="0")

    def test_identity_drift_mtime(self):
        self.assert_refused("identity_drift_mtime", "identity", frees="0")

    def test_identity_drift_ino(self):
        self.assert_refused("identity_drift_ino", "identity", frees="0")


@unittest.skipUnless(RUBY, SKIP_REASON)
class TestTree(GroupTest):
    GROUP = GROUP_TREE

    def test_tree_absent_ok_and_every_inode_queried(self):
        c = self.assert_ok("tree_absent_ok")
        for p in ("/t", "/t/file", "/t/link", "/t/sub", "/t/sub/deep"):
            self.assertIn(p, c["GETS"].split("|"))
        # symlink entry inspected as an entry; no follow to any target
        self.assertNotIn("/t/link/target", c["GETS"])

    def test_tree_deep_present_refuses(self):
        self.assert_refused("tree_acl_present_deep", "acl_present", frees="1")

    def test_tree_dir_identity_change_refuses(self):
        self.assert_refused("tree_dir_identity_changed", "identity")

    def test_tree_child_replacement_refuses(self):
        self.assert_refused("tree_child_replaced", "identity")

    def test_tree_vanished_entry_refuses_not_skipped(self):
        self.assert_refused("tree_entry_vanished", "missing")

    def test_tree_unsupported_entry_refuses_not_skipped(self):
        self.assert_refused("tree_fifo_entry", "unsupported")

    def test_tree_root_file_refuses(self):
        self.assert_refused("tree_root_not_dir", "not_directory")

    def test_tree_root_symlink_not_followed(self):
        self.assert_refused("tree_root_symlink", "not_directory")

    def test_tree_enumeration_error_refuses(self):
        self.assert_refused("tree_traverse_error", "traverse_error")


@unittest.skipUnless(RUBY, SKIP_REASON)
class TestPurePolicyIdentity(GroupTest):
    GROUP = GROUP_PURE

    def test_policy_accepts_valid(self):
        for name in ("policy_ok_one", "policy_ok_tree"):
            c = self.case(name)
            self.assertEqual(c["OK"], "true", name)

    def test_policy_rejects_invalid(self):
        for name in ("policy_unknown_mode", "policy_no_mode",
                     "policy_no_paths", "policy_relative",
                     "policy_nul_in_path", "policy_nul_in_mode"):
            c = self.case(name)
            self.assertEqual(c["OK"], "false", name)
            self.assertEqual(c["REASON"], "usage", name)

    def test_identity_tuple_semantics(self):
        self.assertEqual(self.case("identity_same")["OK"], "true")
        for name in ("identity_uid_diff", "identity_ctime_diff",
                     "identity_nlink_diff"):
            self.assertEqual(self.case(name)["OK"], "false", name)


@unittest.skipUnless(RUBY, SKIP_REASON)
class TestCliMain(unittest.TestCase):
    """Real CLI: usage validation and honest refusal on this host.

    These run the artifact via stdin (`ruby - <mode> <paths>`), exactly the
    documented runtime boundary shape. Validation-only cases never touch
    Fiddle; the absent-path case exercises the real lstat collaborator and
    refuses before any native resolution.
    """

    def test_usage_unknown_mode(self):
        p = run_cli(["wat", "/x"])
        self.assertEqual(p.returncode, 65)
        self.assertIn("refused (usage)", p.stderr)

    def test_usage_relative_path(self):
        p = run_cli(["one", "relative/path"])
        self.assertEqual(p.returncode, 65)
        self.assertIn("refused (usage)", p.stderr)

    def test_usage_no_paths(self):
        p = run_cli(["one"])
        self.assertEqual(p.returncode, 65)
        self.assertIn("refused (usage)", p.stderr)

    def test_missing_path_refused(self):
        p = run_cli(["one", "/nonexistent-native-acl-probe-path"])
        self.assertEqual(p.returncode, 65)
        self.assertIn("refused (missing)", p.stderr)


def main():
    unittest.main(verbosity=2)


if __name__ == "__main__":
    main()


@unittest.skipUnless(RUBY, SKIP_REASON)
class TestParentRegressions(unittest.TestCase):
    def _run(self, ruby):
        with tempfile.TemporaryDirectory(prefix="native_acl_parent_") as temp:
            script = os.path.join(temp, "probe.rb")
            with open(script, "w") as stream:
                stream.write("load ARGV.fetch(0)\n" + ruby)
            return subprocess.run([RUBY, "--disable-gems", "--disable=rubyopt", script, write_reader(temp)],
                                  capture_output=True, text=True, timeout=20)

    def test_allocated_pointer_reaches_free_without_errno_dependency(self):
        p = self._run(r"""
pointer = Object.new
def pointer.null?; false; end
callable = Object.new
callable.define_singleton_method(:call) { |*args| pointer }
resolver = NativeAcl::NativeResolver.new
resolver.instance_variable_set(:@get_link_fn, callable)
def resolver.ensure_functions!; end
def resolver.reset_last_error!; end
def resolver.read_last_error; raise 'errno accessor unavailable'; end
def resolver.acl_free(ptr); @frees = (@frees || 0) + 1; 0; end
begin
  NativeAcl::AclProbe.new(resolver).query('/synthetic')
rescue StandardError
end
puts(resolver.instance_variable_get(:@frees) || 0)
""")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "1")

    def test_directory_changed_to_symlink_refuses_before_enumeration(self):
        scenario = r"""
emit("dir_swap") do |lstat, _resolver, entries|
  lstat.table["/t"] = fstat(kind: :dir, ino: 10)
  lstat.table["/t/sub"] = [fstat(kind: :dir, ino: 11), fstat(kind: :symlink, ino: 12)]
  entries.table["/t"] = ["sub"]
  def entries.children(dir)
    raise 'followed observed symlink' if dir == '/t/sub'
    @table.fetch(dir, [])
  end
  { mode: "tree", paths: ["/t"] }
end
"""
        with tempfile.TemporaryDirectory(prefix="native_acl_parent_") as temp:
            cases = run_ruby_wrapper(scenario, temp)
        self.assertEqual(cases["dir_swap"]["EXIT"], "65")
        self.assertIn(cases["dir_swap"]["REASON"], ("not_directory", "identity"))

    def test_tree_root_identity_is_retained_across_recursion_boundary(self):
        scenario = r"""
emit("root_swap") do |lstat, _resolver, entries|
  lstat.table["/t"] = [fstat(kind: :dir, ino: 10), fstat(kind: :dir, ino: 11)]
  entries.table["/t"] = []
  { mode: "tree", paths: ["/t"] }
end
"""
        with tempfile.TemporaryDirectory(prefix="native_acl_parent_") as temp:
            cases = run_ruby_wrapper(scenario, temp)
        self.assertEqual(cases["root_swap"]["EXIT"], "65")
        self.assertEqual(cases["root_swap"]["REASON"], "identity")


@unittest.skipUnless(sys.platform == "darwin" and os.path.isfile("/usr/bin/ruby"), "Darwin OS Ruby required")
class TestNativeMac(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native_acl_mac_")
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name

    def cli(self, mode, path):
        return subprocess.run(["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "LC_ALL=C", "/usr/bin/ruby",
                               "--disable-gems", "--disable=rubyopt", "-", mode, path],
                              input=reader_source(), text=True, capture_output=True, timeout=20)

    def acl_file(self):
        path = os.path.join(self.root, "owned-acl-file")
        with open(path, "w") as stream:
            stream.write("nonsecret disposable fixture\n")
        os.chmod(path, 0o600)
        acl = subprocess.run(["/bin/chmod", "+a", f"user:{pwd.getpwuid(os.getuid()).pw_name} allow read", path], capture_output=True, text=True)
        self.assertEqual(acl.returncode, 0, acl.stderr)
        return path

    def test_real_absent_file_and_tree(self):
        path = os.path.join(self.root, "owned-file")
        with open(path, "w") as stream:
            stream.write("nonsecret fixture\n")
        os.mkdir(os.path.join(self.root, "sub"))
        result = self.cli("one", path)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli("tree", self.root)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_allocated_acl_refuses_and_free_called_once(self):
        path = self.acl_file()
        definitions = reader_source().split('# Main fires only', 1)[0]
        trace = r"""
class NativeTrace < NativeAcl::NativeResolver
  attr_reader :free_calls, :free_results
  def initialize; @free_calls=0; @free_results=[]; end
  def acl_free(pointer)
    @free_calls += 1
    result = super
    @free_results << result
    result
  end
end
resolver=NativeTrace.new
runner=NativeAcl::Runner.new(resolver: resolver)
result=runner.run(ARGV)
puts [result, runner.last_reason, resolver.free_calls, resolver.free_results.join(',')].join('|')
"""
        result = subprocess.run(["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "LC_ALL=C", "/usr/bin/ruby",
                                 "--disable-gems", "--disable=rubyopt", "-", "one", path],
                                input=definitions+trace, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "65|acl_present|1|0")

    def test_real_symlink_object_does_not_follow_acl_target(self):
        target = self.acl_file()
        tree = os.path.join(self.root, "tree")
        os.mkdir(tree)
        link = os.path.join(tree, "link")
        os.symlink(target, link)
        for mode, path in (("one", link), ("tree", tree)):
            result = self.cli(mode, path)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_real_deep_acl_refuses_tree(self):
        self.acl_file()
        result = self.cli("tree", self.root)
        self.assertEqual(result.returncode, 65, result.stderr)
        self.assertIn("acl_present", result.stderr)

    def test_real_missing_and_enotdir_refuse(self):
        file = os.path.join(self.root, "file")
        with open(file, "w") as stream:
            stream.write("fixture\n")
        for path in (os.path.join(self.root, "missing"), file+"/child"):
            result = self.cli("one", path)
            self.assertEqual(result.returncode, 65, result.stderr)


@unittest.skipUnless(RUBY, SKIP_REASON)
class TestNativeAbiBoundary(unittest.TestCase):
    _run = TestParentRegressions._run

    def test_actual_null_errno_policy_and_reset(self):
        result = self._run(r"""
module Fiddle
  class << self; attr_accessor :last_error; end
end
[Errno::ENOENT::Errno, Errno::ENOTDIR::Errno, Errno::EACCES::Errno,
 Errno::EIO::Errno, 0, nil, '2'].each do |errno|
  pointer=Object.new
  def pointer.null?; true; end
  callable=Object.new
  callable.define_singleton_method(:call) do |*args|
    raise 'errno not reset' unless Fiddle.last_error == 0
    Fiddle.last_error=errno
    pointer
  end
  resolver=NativeAcl::NativeResolver.new
  resolver.instance_variable_set(:@get_link_fn, callable)
  def resolver.ensure_functions!; end
  Fiddle.last_error=999
  begin
    puts resolver.get_link('/synthetic')
  rescue NativeAcl::Refusal => failure
    puts failure.reason
  end
end
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ['absent', 'acl_error', 'acl_error', 'acl_error', 'acl_error', 'runtime', 'runtime'])

    def test_missing_errno_reset_api_refuses_before_native_call(self):
        result = self._run(r"""
module Fiddle
  def self.last_error; 2; end
end
resolver=NativeAcl::NativeResolver.new
def resolver.ensure_functions!; end
begin
  resolver.get_link('/synthetic')
rescue NativeAcl::Refusal => failure
  puts failure.reason
end
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'runtime')
