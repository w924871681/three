"""Pure command-string contracts; no process query, launch, stop, or wait.

Only allowed_commands is called. Native observers and delivery entry points are
never constructed or invoked by these tests.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
BASE_EXE = r'C:\Users\92487\anaconda3\envs\rcf-dti-py311\python.exe'
VENV_EXE = r'D:\dt-talk\DT_LIFECYCLE_ESCALATION\verification\paper3_canonical_inputs\model_env_recovery_v1_20261009\P7_7_REPLICATION_MODEL_ENV_V1\Scripts\python.exe'
SEQUENCE = r'D:\dt-talk\DT_LIFECYCLE_ESCALATION\verification\paper3_canonical_inputs\replication_dynamic_takeover_v1\dynamic_sequence.py'
PLAN = str(HERE / 'RECOVERY_DELIVERY_PLAN_001.json')
COMMAND = [VENV_EXE, '-I', '-S', '-B', '-X',
           r'pycache_prefix=D:\dt-talk\DT_LIFECYCLE_ESCALATION\results\p7_7_integrity_replication_batch20_env_v3\_dynamic_delivery_recovery001_cache\never_pycache',
           SEQUENCE, 'execute', '--plan', PLAN]


class CommandMatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        name = 'paper3_native_observer_pure_matcher_tests'
        spec = importlib.util.spec_from_file_location(name, HERE / 'native_observer.py')
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[name] = cls.module
        with mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('no process calls in matcher tests')):
            spec.loader.exec_module(cls.module)

    def variants(self, command=None, base=BASE_EXE):
        with mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('no process calls in matcher tests')):
            return self.module.allowed_commands(COMMAND if command is None else command, base)

    def quoted_base(self):
        return '"' + BASE_EXE + '" ' + subprocess.list2cmdline(COMMAND[1:])

    def test_exact_three_forms_only(self):
        self.assertEqual(self.variants(), {
            subprocess.list2cmdline(COMMAND),
            subprocess.list2cmdline([BASE_EXE, *COMMAND[1:]]),
            self.quoted_base(),
        })

    def test_original_venv_form_accepted(self):
        self.assertIn(subprocess.list2cmdline(COMMAND), self.variants())

    def test_base_redirector_form_accepted(self):
        self.assertIn(subprocess.list2cmdline([BASE_EXE, *COMMAND[1:]]), self.variants())

    def test_actual_quoted_base_form_accepted(self):
        self.assertIn(self.quoted_base(), self.variants())

    def test_base_path_object_accepted(self):
        self.assertEqual(self.variants(base=Path(BASE_EXE)), self.variants())

    def test_input_arguments_unchanged(self):
        before = list(COMMAND)
        self.variants(COMMAND)
        self.assertEqual(COMMAND, before)

    def test_extra_flag_rejected(self):
        self.assertNotIn(self.quoted_base() + ' --extra', self.variants())

    def test_inserted_flag_rejected(self):
        altered = [BASE_EXE, '-E', *COMMAND[1:]]
        self.assertNotIn(subprocess.list2cmdline(altered), self.variants())

    def test_missing_isolation_flag_rejected(self):
        altered = [BASE_EXE, *[part for part in COMMAND[1:] if part != '-I']]
        self.assertNotIn(subprocess.list2cmdline(altered), self.variants())

    def test_flag_order_changed_rejected(self):
        altered = [BASE_EXE, '-S', '-I', *COMMAND[3:]]
        self.assertNotIn(subprocess.list2cmdline(altered), self.variants())

    def test_different_plan_rejected(self):
        self.assertNotIn(self.quoted_base().replace('RECOVERY_DELIVERY_PLAN_001.json', 'RECOVERY_DELIVERY_PLAN_002.json'), self.variants())

    def test_different_executable_rejected(self):
        self.assertNotIn(self.quoted_base().replace('rcf-dti-py311', 'other-env', 1), self.variants())

    def test_executable_suffix_rejected(self):
        self.assertNotIn(self.quoted_base().replace('python.exe"', 'python.exe.bak"', 1), self.variants())

    def test_case_changed_executable_rejected(self):
        self.assertNotIn(self.quoted_base().replace('python.exe"', 'PYTHON.EXE"', 1), self.variants())

    def test_different_sequence_source_rejected(self):
        self.assertNotIn(self.quoted_base().replace('dynamic_sequence.py', 'other_sequence.py'), self.variants())

    def test_different_action_rejected(self):
        self.assertNotIn(self.quoted_base().replace(' execute ', ' verify-plan '), self.variants())

    def test_extra_space_after_executable_rejected(self):
        self.assertNotIn(self.quoted_base().replace('" -I', '"  -I', 1), self.variants())

    def test_extra_parameter_space_rejected(self):
        self.assertNotIn(self.quoted_base().replace(' -S ', '  -S ', 1), self.variants())

    def test_leading_space_rejected(self):
        self.assertNotIn(' ' + self.quoted_base(), self.variants())

    def test_trailing_space_rejected(self):
        self.assertNotIn(self.quoted_base() + ' ', self.variants())

    def test_quoted_plan_parameter_rejected(self):
        self.assertNotIn(self.quoted_base().replace(' --plan ' + PLAN, ' --plan "' + PLAN + '"'), self.variants())

    def test_quoted_flag_rejected(self):
        self.assertNotIn(self.quoted_base().replace(' -I ', ' "-I" ', 1), self.variants())

    def test_single_quoted_base_rejected(self):
        self.assertNotIn("'" + BASE_EXE + "' " + subprocess.list2cmdline(COMMAND[1:]), self.variants())

    def test_quoted_venv_is_not_additionally_admitted(self):
        self.assertNotIn('"' + VENV_EXE + '" ' + subprocess.list2cmdline(COMMAND[1:]), self.variants())

    def test_incomplete_quote_rejected(self):
        self.assertNotIn('"' + BASE_EXE + ' ' + subprocess.list2cmdline(COMMAND[1:]), self.variants())

    def test_changed_cache_parameter_rejected(self):
        self.assertNotIn(self.quoted_base().replace('never_pycache', 'other_pycache'), self.variants())


if __name__ == '__main__':
    unittest.main(verbosity=2)
