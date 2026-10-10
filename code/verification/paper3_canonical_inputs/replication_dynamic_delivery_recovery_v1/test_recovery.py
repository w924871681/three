"""Independent, synthetic-only tests of the new delivery recovery launcher.

This file does not read scientific arrays or results, run a guard, or start any
process. It tests environment and command construction with isolated inputs.
The coordinator separately owns real interpreter/guard integration probes.
"""
from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
REPO = Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
V1 = REPO / "verification/paper3_canonical_inputs/replication_dynamic_takeover_v1"
MODEL_PYTHON = (
    REPO / "verification/paper3_canonical_inputs/model_env_recovery_v1_20261009"
    / "P7_7_REPLICATION_MODEL_ENV_V1/Scripts/python.exe"
)
METADATA_PYTHON = Path(r"C:\Users\92487\anaconda3\envs\rcf-dti-py311\python.exe")

# The key names mirror the frozen manifest, but these fixtures neither load nor
# mutate it. Non-null cases below are synthetic API tests, not new protocol values.
THREAD_KEYS = (
    "BLIS_NUM_THREADS", "MKL_CBWR", "MKL_DYNAMIC", "MKL_NUM_THREADS",
    "NPY_DISABLE_CPU_FEATURES", "NUMEXPR_NUM_THREADS", "OMP_DYNAMIC",
    "OMP_NUM_THREADS", "OPENBLAS_CORETYPE", "OPENBLAS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)
RUNTIME_KEYS = (
    "BLIS_NUM_THREADS", "CUBLAS_WORKSPACE_CONFIG", "CUDA_DEVICE_ORDER",
    "CUDA_VISIBLE_DEVICES", "KMP_AFFINITY", "KMP_BLOCKTIME",
    "KMP_DUPLICATE_LIB_OK", "KMP_INIT_AT_FORK", "KMP_SETTINGS", "MKL_CBWR",
    "MKL_DYNAMIC", "MKL_INTERFACE_LAYER", "MKL_NUM_THREADS",
    "MKL_SERVICE_FORCE_INTEL", "MKL_THREADING_LAYER", "NPY_DISABLE_CPU_FEATURES",
    "NUMEXPR_MAX_THREADS", "NUMEXPR_NUM_THREADS", "NVIDIA_TF32_OVERRIDE",
    "OMP_DYNAMIC", "OMP_NUM_THREADS", "OMP_PLACES", "OMP_PROC_BIND",
    "OMP_SCHEDULE", "OMP_WAIT_POLICY", "OPENBLAS_CORETYPE",
    "OPENBLAS_NUM_THREADS", "PYTORCH_ALLOC_CONF", "PYTORCH_CUDA_ALLOC_CONF",
    "PYTORCH_NO_CUDA_MEMORY_CACHING", "TORCH_ALLOW_TF32_CUBLAS_OVERRIDE",
    "TORCH_CUDNN_V8_API_DISABLED", "TORCH_CUDNN_V8_API_LRU_CACHE_LIMIT",
    "VECLIB_MAXIMUM_THREADS",
)


def environment_fixture():
    return {
        "python_executable": str(MODEL_PYTHON),
        "thread_environment": {key: None for key in THREAD_KEYS},
        "model_runtime_environment": {key: None for key in RUNTIME_KEYS},
    }


def load_recovery():
    # Register before execution so standard-library dataclasses can resolve the
    # module. recovery.py must itself remain import safe, with its main guarded.
    name = "paper3_delivery_recovery_synthetic_tests"
    spec = importlib.util.spec_from_file_location(name, HERE / "recovery.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("New recovery implementation is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


r = load_recovery()


class RecoveryConstructionTests(unittest.TestCase):
    def setUp(self):
        self.environment = environment_fixture()
        self.temporary = tempfile.TemporaryDirectory(prefix="paper3_recovery_synthetic_")
        self.addCleanup(self.temporary.cleanup)
        self.cache = Path(self.temporary.name) / "independent_cache"
        self.plan = Path(self.temporary.name) / "new_plan.json"

    def test_all_frozen_thread_nulls_remove_parent_values(self):
        parent = {key: "PARENT_MUST_NOT_LEAK" for key in THREAD_KEYS}
        value = r.build_env(self.environment, self.cache, parent=parent)
        self.assertTrue(set(THREAD_KEYS).isdisjoint(value))

    def test_all_frozen_runtime_nulls_remove_parent_values(self):
        parent = {key: "PARENT_MUST_NOT_LEAK" for key in RUNTIME_KEYS}
        value = r.build_env(self.environment, self.cache, parent=parent)
        self.assertTrue(set(RUNTIME_KEYS).isdisjoint(value))

    def test_parent_mkl_cbwr_auto_is_removed_for_frozen_null(self):
        value = r.build_env(self.environment, self.cache, parent={"MKL_CBWR": "AUTO"})
        self.assertNotIn("MKL_CBWR", value)

    def test_parent_omp_mkl_blas_and_backend_values_are_not_normalized(self):
        parent = {
            "OMP_NUM_THREADS": "8", "MKL_NUM_THREADS": "8",
            "OPENBLAS_NUM_THREADS": "32", "NVIDIA_TF32_OVERRIDE": "1",
            "TORCH_ALLOW_TF32_CUBLAS_OVERRIDE": "1", "KMP_DUPLICATE_LIB_OK": "True",
        }
        value = r.build_env(self.environment, self.cache, parent=parent)
        self.assertTrue(set(parent).isdisjoint(value))

    def test_runtime_cuda_selection_null_does_not_inherit_parent(self):
        parent = {"CUDA_VISIBLE_DEVICES": "1", "CUDA_DEVICE_ORDER": "PCI_BUS_ID"}
        value = r.build_env(self.environment, self.cache, parent=parent)
        self.assertTrue(set(parent).isdisjoint(value))

    def test_nonnull_thread_value_is_exactly_preserved(self):
        self.environment["thread_environment"]["OMP_NUM_THREADS"] = "3"
        self.environment["model_runtime_environment"]["OMP_NUM_THREADS"] = "3"
        value = r.build_env(self.environment, self.cache, parent={"OMP_NUM_THREADS": "99"})
        self.assertEqual(value["OMP_NUM_THREADS"], "3")

    def test_nonnull_runtime_value_is_exactly_preserved(self):
        self.environment["model_runtime_environment"]["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
        value = r.build_env(self.environment, self.cache, parent={"CUBLAS_WORKSPACE_CONFIG": "wrong"})
        self.assertEqual(value["CUBLAS_WORKSPACE_CONFIG"], ":4096:8")

    def test_bound_case_and_whitespace_are_not_silently_changed(self):
        self.environment["model_runtime_environment"]["KMP_AFFINITY"] = "  SYNTHETIC,ExactCase  "
        value = r.build_env(self.environment, self.cache, parent={})
        self.assertEqual(value["KMP_AFFINITY"], "  SYNTHETIC,ExactCase  ")

    def test_empty_bound_string_is_not_treated_as_null(self):
        self.environment["model_runtime_environment"]["CUDA_VISIBLE_DEVICES"] = ""
        value = r.build_env(self.environment, self.cache, parent={"CUDA_VISIBLE_DEVICES": "9"})
        self.assertIn("CUDA_VISIBLE_DEVICES", value)
        self.assertEqual(value["CUDA_VISIBLE_DEVICES"], "")

    def test_nonnull_binding_is_added_when_parent_lacks_key(self):
        self.environment["model_runtime_environment"]["OMP_PLACES"] = "cores"
        value = r.build_env(self.environment, self.cache, parent={})
        self.assertEqual(value["OMP_PLACES"], "cores")

    def test_parent_mapping_is_not_mutated(self):
        parent = {"OMP_NUM_THREADS": "8", "PATH": "SYNTHETIC_PATH", "TEMP": "OLD_TEMP"}
        before = copy.deepcopy(parent)
        r.build_env(self.environment, self.cache, parent=parent)
        self.assertEqual(parent, before)

    def test_frozen_environment_fixture_is_not_mutated(self):
        before = copy.deepcopy(self.environment)
        r.build_env(self.environment, self.cache, parent={"MKL_CBWR": "AUTO"})
        self.assertEqual(self.environment, before)

    def test_explicit_parent_does_not_change_process_environment(self):
        before = dict(os.environ)
        r.build_env(self.environment, self.cache, parent={"OMP_NUM_THREADS": "8"})
        self.assertEqual(dict(os.environ), before)

    def test_returned_environment_is_independent_of_parent(self):
        parent = {"PATH": "SYNTHETIC_PATH"}
        value = r.build_env(self.environment, self.cache, parent=parent)
        value["PATH"] = "CHANGED_RETURN_ONLY"
        self.assertEqual(parent["PATH"], "SYNTHETIC_PATH")

    def test_unrelated_parent_keys_are_preserved(self):
        parent = {"PATH": "SYNTHETIC_PATH", "SYSTEMROOT": "SYNTHETIC_SYSTEMROOT"}
        value = r.build_env(self.environment, self.cache, parent=parent)
        self.assertEqual(value["PATH"], parent["PATH"])
        self.assertEqual(value["SYSTEMROOT"], parent["SYSTEMROOT"])

    def test_empty_explicit_parent_does_not_fall_back_to_os_environment(self):
        with patch.dict(os.environ, {"PAPER3_SYNTHETIC_PARENT_SENTINEL": "MUST_NOT_LEAK"}):
            value = r.build_env(self.environment, self.cache, parent={})
        self.assertNotIn("PAPER3_SYNTHETIC_PARENT_SENTINEL", value)

    def test_default_parent_is_copied_then_bound_nulls_removed(self):
        parent = {"PATH": "SYNTHETIC_PATH", "OMP_NUM_THREADS": "99", "KMP_INIT_AT_FORK": "FALSE"}
        with patch.dict(os.environ, parent, clear=True):
            before = dict(os.environ)
            value = r.build_env(self.environment, self.cache)
            self.assertEqual(dict(os.environ), before)
        self.assertEqual(value["PATH"], "SYNTHETIC_PATH")
        self.assertNotIn("OMP_NUM_THREADS", value)
        self.assertNotIn("KMP_INIT_AT_FORK", value)

    def test_four_cache_variables_point_only_to_independent_root(self):
        parent = {name: str(REPO / "results/p7_7") for name in ("TEMP", "TMP", "TORCH_HOME", "CUDA_CACHE_PATH")}
        value = r.build_env(self.environment, self.cache, parent=parent)
        expected = {"TEMP": self.cache / "temp", "TMP": self.cache / "temp",
                    "TORCH_HOME": self.cache / "torch", "CUDA_CACHE_PATH": self.cache / "cuda"}
        for name, path in expected.items():
            with self.subTest(name=name):
                self.assertEqual(value[name], str(path))
                self.assertTrue(Path(value[name]).is_relative_to(self.cache))
                self.assertNotEqual(value[name], parent[name])

    def test_different_cache_roots_produce_distinct_cache_bindings(self):
        other = Path(self.temporary.name) / "other_independent_cache"
        one = r.build_env(self.environment, self.cache, parent={})
        two = r.build_env(self.environment, other, parent={})
        for name in ("TEMP", "TMP", "TORCH_HOME", "CUDA_CACHE_PATH"):
            with self.subTest(name=name):
                self.assertNotEqual(one[name], two[name])
                self.assertTrue(Path(two[name]).is_relative_to(other))

    def test_command_exactly_matches_authorized_original_entry(self):
        expected = [str(MODEL_PYTHON), "-I", "-S", "-B", "-X",
                    "pycache_prefix=" + str(self.cache / "never_pycache"),
                    str(V1 / "dynamic_sequence.py"), "execute", "--plan", str(self.plan)]
        self.assertEqual(r.build_command(self.environment, self.plan, self.cache), expected)

    def test_command_uses_bound_venv_and_not_metadata_python(self):
        command = r.build_command(self.environment, self.plan, self.cache)
        self.assertEqual(command[0], self.environment["python_executable"])
        self.assertEqual(command[0], str(MODEL_PYTHON))
        self.assertNotEqual(command[0], str(METADATA_PYTHON))

    def test_command_does_not_substitute_current_test_interpreter(self):
        synthetic_python = Path(self.temporary.name) / "synthetic_bound_venv/Scripts/python.exe"
        self.environment["python_executable"] = str(synthetic_python)
        command = r.build_command(self.environment, self.plan, self.cache)
        self.assertEqual(command[0], str(synthetic_python))
        self.assertNotEqual(command[0], sys.executable)

    def test_command_binds_new_plan_path_exactly(self):
        other_plan = Path(self.temporary.name) / "separate attempt/new reviewed plan.json"
        first = r.build_command(self.environment, self.plan, self.cache)
        second = r.build_command(self.environment, other_plan, self.cache)
        self.assertEqual(second[-2:], ["--plan", str(other_plan)])
        self.assertEqual(first[:-1], second[:-1])
        self.assertNotEqual(first[-1], second[-1])

    def test_command_binds_cache_as_one_literal_x_argument(self):
        cache = Path(self.temporary.name) / "cache with spaces"
        command = r.build_command(self.environment, self.plan, cache)
        self.assertEqual(command[4:6], ["-X", "pycache_prefix=" + str(cache / "never_pycache")])
        self.assertEqual(len(command), 10)

    def test_command_remains_an_argv_list_without_shell_quoting(self):
        plan = Path(self.temporary.name) / "plan with spaces and & literal.json"
        command = r.build_command(self.environment, plan, self.cache)
        self.assertIsInstance(command, list)
        self.assertTrue(all(isinstance(value, str) for value in command))
        self.assertEqual(command[-1], str(plan))
        self.assertNotIn("cmd.exe", command)
        self.assertNotIn("powershell.exe", command)

    def test_command_construction_mutates_neither_environment_nor_paths(self):
        before = copy.deepcopy(self.environment)
        r.build_command(self.environment, self.plan, self.cache)
        self.assertEqual(self.environment, before)
        self.assertFalse(self.plan.exists())
        self.assertFalse(self.cache.exists())


if __name__ == "__main__":
    unittest.main()
