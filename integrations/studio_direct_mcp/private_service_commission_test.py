from __future__ import annotations
import hashlib, importlib.util, json, stat, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
SOURCE=Path(__file__).with_name("private_service.py")
spec=importlib.util.spec_from_file_location("svc",SOURCE);svc=importlib.util.module_from_spec(spec);spec.loader.exec_module(svc)
def config_value(account="test-account",port=45025,uid=501):
 return {"schema":"mastermind.os_commission_publication.v1","release_sha":"a"*40,"studio_uid":uid,"studio_account":account,"studio_port":port,"policy":{},"grants":[],"base_sha":"b"*40,"audit_directory":"/var/empty","auth_helper_sha256":"c"*64,"file_helper_sha256":"d"*64}
class T(unittest.TestCase):
 def seal(self,c,owner=0):
  def f(p):
   return SimpleNamespace(st_uid=owner,st_mode=(stat.S_IFREG if p==c else stat.S_IFDIR)|0o700,st_nlink=1)
  return f
 def a(self,d=None):return SimpleNamespace(account="test-account",port=45025,enable_repository_workspaces=True,os_commission_config_sha256=d)
 def test_default_off(self):
  with tempfile.TemporaryDirectory() as d:
   c=Path(d)/"missing"
   with mock.patch.object(svc,"OS_COMMISSION_CONFIG",c):self.assertIsNone(svc._commission_setting(self.a(),{"config":Path(d)/"x"},None))
 def test_sealed_exact_and_rejections(self):
  with tempfile.TemporaryDirectory() as d:
   c=Path(d)/"sealed";raw=json.dumps(config_value()).encode();c.write_bytes(raw);h=hashlib.sha256(raw).hexdigest()
   with mock.patch.object(svc,"OS_COMMISSION_CONFIG",c),mock.patch("pathlib.Path.lstat",self.seal(c)),mock.patch.object(svc.os,"getuid",return_value=501),mock.patch.object(svc.os,"geteuid",return_value=501):
    self.assertEqual(svc._commission_setting(self.a(h),{"config":Path(d)/"x"},None),h)
    with self.assertRaises(SystemExit):svc._commission_setting(self.a("0"*64),{"config":Path(d)/"x"},None)
    c.write_bytes(json.dumps(config_value(account="foreign")).encode())
    with self.assertRaises(SystemExit):svc._commission_setting(self.a(hashlib.sha256(c.read_bytes()).hexdigest()),{"config":Path(d)/"x"},None)
   c.write_bytes(raw)
   with mock.patch.object(svc,"OS_COMMISSION_CONFIG",c),mock.patch("pathlib.Path.lstat",self.seal(c,501)),mock.patch.object(svc.os,"getuid",return_value=501),mock.patch.object(svc.os,"geteuid",return_value=501):
    with self.assertRaises(SystemExit):svc._commission_setting(self.a(h),{"config":Path(d)/"x"},None)
 def test_prior_tamper_refused(self):
  with tempfile.TemporaryDirectory() as d:
   c=Path(d)/"runtime";c.write_text(json.dumps({"commissionPublication":{"enabled":True,"configurationDigest":"d"*64}}));prior={"configHash":svc._sha256_file(c)};c.write_text("{}")
   with self.assertRaises(SystemExit):svc._commission_setting(self.a(),{"config":c},prior)
if __name__=="__main__":unittest.main()