"""Small adversarial tests: no production CSV reads and no new statistics."""
import importlib.util
import json
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('independent_statistic_verifier',HERE/'verify_statistics.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class MemoryEvidence(module.Evidence):
    def __init__(self,text): super().__init__();self.payload=text.encode()
    def read(self,*args,**kwargs): return self.payload

class AdversarialComparison(unittest.TestCase):
    def compare(self,text,expected): return MemoryEvidence(text).compare('synthetic.csv',expected,('method',))
    def test_exact_pass(self): self.compare('method,value\nB8,0.0029126269437559434\n',[{'method':'B8','value':0.0029126269437559434}])
    def test_changed_scientific_value_rejected(self):
        with self.assertRaises(RuntimeError): self.compare('method,value\nB8,0.0028126269437559434\n',[{'method':'B8','value':0.0029126269437559434}])
    def test_missing_row_rejected(self):
        with self.assertRaises(RuntimeError): self.compare('method,value\nB8,1\n',[{'method':'B8','value':1},{'method':'P7.7','value':1}])
    def test_duplicate_row_rejected(self):
        with self.assertRaises(RuntimeError): self.compare('method,value\nB8,1\nB8,1\n',[{'method':'B8','value':1}])
    def test_nonfinite_rejected(self):
        with self.assertRaises(RuntimeError): self.compare('method,value\nB8,nan\n',[{'method':'B8','value':1}])
    def test_estimate_definition_change_rejected(self):
        with self.assertRaises(RuntimeError): self.compare('method,value\nB8,BOOTSTRAP_MEAN\n',[{'method':'B8','value':'OBSERVED_METHOD_CENTER_MEAN_SUBTRACTION'}])
    def test_unexpected_column_rejected(self):
        with self.assertRaises(RuntimeError): self.compare('method,value,extra\nB8,1,x\n',[{'method':'B8','value':1}])
    def test_duplicate_header_rejected(self):
        with self.assertRaises(RuntimeError): self.compare('method,value,value\nB8,1,1\n',[{'method':'B8','value':1}])

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(AdversarialComparison)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    import sys
    sys.exit(0 if result.wasSuccessful() else 1)
