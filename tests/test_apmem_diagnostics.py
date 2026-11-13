import unittest
import numpy as np
from research.apmem_shadow.diagnostics import block_mean_interval

class DiagnosticTests(unittest.TestCase):
    def test_constant_difference(self):
        z=block_mean_interval(np.ones(200)*-.5,20,repetitions=100)
        self.assertEqual(z['pointwise_95pct_interval'],[-.5,-.5])
        self.assertFalse(z['prospective_validation'])
    def test_determinism(self):
        x=np.linspace(-1,1,200)
        self.assertEqual(block_mean_interval(x,20,repetitions=100),block_mean_interval(x,20,repetitions=100))
    def test_invalid_input(self):
        for x in ([1],[1,float('nan')]):
            with self.assertRaises(ValueError):block_mean_interval(x,1,repetitions=100)
    def test_invalid_block(self):
        with self.assertRaises(ValueError):block_mean_interval(np.ones(10),11,repetitions=100)

if __name__=='__main__':unittest.main()
