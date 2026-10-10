"""Synthetic correction regressions. No real input or experiment execution."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

path = Path(__file__).with_name('binding_corrector_001.py')
spec = importlib.util.spec_from_file_location('binding_corrector_under_test', path)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class CorrectionTests(unittest.TestCase):
    def fixture(self):
        value = {'schema': 'paper3-abrupt-recovery-gate-v1', 'status': 'PASS',
                 'source_bindings_sha256': {'existing': 'keep'},
                 'evidence_sha256': {str(b.ROOT / p): h for p, h in b.ADDITIONS.items()},
                 'scientific_identity': {'input': 'same', 'workers': 2}}
        value['gate_digest'] = b.canonical(value)
        return value

    def checked(self, value):
        return b.corrected(value, hash_file=lambda p: b.ADDITIONS[p.relative_to(b.ROOT).as_posix()])

    def test_only_three_classification_additions(self):
        old = self.fixture()
        before = copy.deepcopy(old)
        new = self.checked(old)
        self.assertEqual(old, before)
        self.assertEqual(len(new['source_bindings_sha256']), len(old['source_bindings_sha256']) + 3)
        self.assertEqual(new['evidence_sha256'], old['evidence_sha256'])
        self.assertEqual(new['scientific_identity'], old['scientific_identity'])

    def test_digest_binds_new_fields(self):
        value = self.checked(self.fixture())
        digest = value.pop('gate_digest')
        self.assertEqual(digest, b.canonical(value))

    def test_original_digest_required(self):
        value = self.fixture()
        value['gate_digest'] = 'wrong'
        with self.assertRaises(RuntimeError): self.checked(value)

    def test_missing_old_evidence_rejected(self):
        value = self.fixture()
        value['evidence_sha256'] = {}
        value.pop('gate_digest'); value['gate_digest'] = b.canonical(value)
        with self.assertRaises(RuntimeError): self.checked(value)

    def test_wrong_actual_source_rejected(self):
        with self.assertRaises(RuntimeError): b.corrected(self.fixture(), hash_file=lambda p: 'wrong')

    def test_double_correction_rejected(self):
        with self.assertRaises(RuntimeError): self.checked(self.checked(self.fixture()))

    def test_exclusive_output(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'receipt.json'
            b.emit(path, {'original': True})
            original = path.read_bytes()
            with self.assertRaises(FileExistsError): b.emit(path, {'overwrite': True})
            self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
