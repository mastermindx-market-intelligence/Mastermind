import json,hashlib,unittest
from pathlib import Path
import support_bundle,artifact_production
class Support(unittest.TestCase):
 def test_exact_support_generation_and_artifact_digest_agree(self):
  here=Path(__file__).parent
  names=frozenset((here/'remote_sub.sh').read_text().split('SUPPORT_FILES=(',1)[1].split(')',1)[0].split())
  self.assertEqual(names,support_bundle.SOURCE_FILES)
  self.assertIn(names,support_bundle.SOURCE_GENERATIONS)
  self.assertNotIn(names-{'fabric_operator_stop.py'},support_bundle.SOURCE_GENERATIONS)
  self.assertIn(support_bundle.PRE_OPERATOR_SOURCE_FILES,support_bundle.SOURCE_GENERATIONS)
 def test_artifact_combination_refuses_before_effects(self):
  text=(Path(__file__).parent/'remote_sub.sh').read_text()
  self.assertLess(text.index('OPERATOR_ARTIFACT_COMBINATION_UNSUPPORTED'),text.index('acquire --'))
if __name__=='__main__':unittest.main()
