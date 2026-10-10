"""Independent, synthetic-only statistical and guard tests; no project imports.

These tests never read actual old/new outcomes, run a model/generator or call
the real statistics entry. Optional evidence is exclusively published here.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
import types
import unittest
from datetime import datetime,timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGE = "paper3_statistics_synthetic_env_v3"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package
def load(name):
    spec = importlib.util.spec_from_file_location(PACKAGE+"."+name,ROOT/(name+".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
S = load("statistics")
G = load("runtime_guard")
CENTERS = (7,9,13)
SEEDS = (11,12)
SCENARIOS = ("C0","C4")
METHODS = S.METHODS
STAGES = 2
CONTRACT = dict(centers=CENTERS,seeds=SEEDS,scenarios=SCENARIOS,methods=METHODS,stages=STAGES)
SELECTED_SITE = None


def synthetic_rows():
    result = []
    for m,method in enumerate(METHODS):
        for c,center in enumerate(CENTERS):
            for s,seed in enumerate(SEEDS):
                for q,scenario in enumerate(SCENARIOS):
                    for stage in range(1,STAGES+1):
                        action = "retain" if stage==1 else ("ri" if method=="P7.7" else "local")
                        result.append(dict(method=method,center_id=center,seed=seed,scenario=scenario,stage=stage,
                            service_mse=float(10*c+s+q+stage+m),action=action,gate_open=int(action=="ri"),
                            event_cost_raw=.2 if action=="ri" else .02 if action=="local" else 0.,
                            best_local_policy="P0" if stage==1 else "P50",R_B50=-1. if stage==2 else 1.,
                            feasible_candidate_count=3,ri_search_updates_charged=150 if action=="ri" else 0,
                            source_cache_hits=1,shared_parent_cache_hit=stage==1,
                            decision_runtime_actual_s=.25,decision_runtime_standalone_estimate_s=.5))
    return result


class AggregationTests(unittest.TestCase):
    def setUp(self): self.rows = synthetic_rows()
    def aggregate(self,rows=None): return S.aggregate_rows(self.rows if rows is None else rows,service_unit=.2,**CONTRACT)
    def reject(self,mutate):
        rows = copy.deepcopy(self.rows); mutate(rows)
        with self.assertRaises(S.StatisticsIntegrityError): self.aggregate(rows)
    def test_hierarchical_center_mean(self):
        data = self.aggregate(); point = next(r for r in data["center"] if r["method"]=="B0" and r["center_id"]==7)
        self.assertEqual(point["lifecycle_service_loss"],2.5)
        self.assertEqual(len(data["trajectory"]),60); self.assertEqual(len(data["center"]),15)
        self.assertEqual(len(data["scenario_center"]),30)
    def test_stage_count_and_action_partition(self):
        for row in self.aggregate()["trajectory"]:
            self.assertEqual(row["retain_count"]+row["maintenance_count"]+row["ri_count"],2)
            self.assertEqual(row["retain_rate"]+row["maintenance_rate"]+row["ri_rate"],1.)
    def test_cost_not_added_to_endpoint(self):
        data = self.aggregate(); p = next(r for r in data["trajectory"] if r["method"]=="P7.7")
        self.assertEqual(p["lifecycle_service_loss"],5.5); self.assertEqual(p["total_action_cost"],.2)
    def test_duplicate_stage_rejected(self): self.reject(lambda rows:rows.append(dict(rows[0])))
    def test_missing_stage_rejected(self): self.reject(lambda rows:rows.pop(0))
    def test_missing_trajectory_rejected(self): self.reject(lambda rows:rows.__delitem__(slice(0,2)))
    def test_unknown_method_rejected(self): self.reject(lambda rows:rows[0].__setitem__("method","other"))
    def test_unknown_center_rejected(self): self.reject(lambda rows:rows[0].__setitem__("center_id",8))
    def test_noninteger_stage_rejected(self): self.reject(lambda rows:rows[0].__setitem__("stage",1.5))
    def test_nan_loss_rejected(self): self.reject(lambda rows:rows[0].__setitem__("service_mse",float("nan")))
    def test_infinite_diagnostic_rejected(self): self.reject(lambda rows:rows[0].__setitem__("R_B50",float("inf")))
    def test_negative_loss_rejected(self): self.reject(lambda rows:rows[0].__setitem__("service_mse",-1.))
    def test_negative_cost_rejected(self): self.reject(lambda rows:rows[0].__setitem__("event_cost_raw",-1.))
    def test_invalid_gate_rejected(self): self.reject(lambda rows:rows[0].__setitem__("gate_open",2))
    def test_invalid_action_rejected(self): self.reject(lambda rows:rows[0].__setitem__("action","unknown"))
    def test_ri_without_gate_rejected(self): self.reject(lambda rows:rows[-1].__setitem__("gate_open",0))
    def test_fixed_action_unit_rejected(self): self.reject(lambda rows:rows[1].__setitem__("event_cost_raw",.03))
    def test_offline_diagnostic_boundary_and_overlap(self):
        for row in self.rows:
            if row["method"]=="P7.7": row["R_B50"] = -1. if row["stage"]==1 else 0.
        diag = {row["metric"]:row for row in self.aggregate()["diagnostics"]}
        self.assertEqual(diag["correct retain"]["count"],12)
        self.assertEqual(diag["missed escalation"]["count"],12)
        self.assertEqual(diag["unnecessary RI"]["count"],12)
        self.assertEqual(diag["correct escalation"]["count"],0)
        self.assertEqual(diag["missed escalation"]["denominator"],24)
    def test_input_rows_unchanged(self):
        before = copy.deepcopy(self.rows); self.aggregate(); self.assertEqual(before,self.rows)


class BootstrapTests(unittest.TestCase):
    def setUp(self): self.data = S.aggregate_rows(synthetic_rows(),**CONTRACT)
    def tables(self,data=None,draws=31): return S.joint_center_tables(self.data if data is None else data,centers=CENTERS,methods=METHODS,scenarios=SCENARIOS,draws=draws,seed=2904)
    def test_joint_shape_seed_repeatability(self):
        import numpy as np
        a,b = self.tables(),self.tables(); self.assertEqual(a["indices"].shape,(31,3))
        np.testing.assert_array_equal(a["indices"],b["indices"])
    def test_shared_resamples_preserve_constant_paired_difference(self):
        tables = self.tables()
        for row in tables["bootstrap"]:
            expected = 4-METHODS.index(row["comparison"].split(" - ")[1])
            self.assertAlmostEqual(row["difference"],expected)
        for row in tables["contrasts"]: self.assertAlmostEqual(row["ci_low"],row["ci_high"])
    def test_all_method_draws_use_same_indices(self):
        import numpy as np
        tables = self.tables(); indices = tables["indices"]
        for method in METHODS:
            means = [next(r for r in self.data["center"] if r["method"]==method and r["center_id"]==c)["lifecycle_service_loss"] for c in CENTERS]
            expected = np.asarray(means)[indices].mean(axis=1)
            actual = [r["lifecycle_service_loss"] for r in tables["method_bootstrap"] if r["method"]==method]
            np.testing.assert_allclose(actual,expected,rtol=0,atol=0)
    def test_point_estimate_original_means_not_bootstrap_average(self):
        for row in self.data["center"]:
            if row["method"]=="P7.7" and row["center_id"]==13: row["lifecycle_service_loss"]+=100
        tables = self.tables(draws=1); means = {r["method"]:r["mean_lifecycle_service_loss"] for r in tables["method"]}
        contrast = tables["contrasts"][0]
        self.assertEqual(contrast["mean_difference"],means["P7.7"]-means["B0"])
        self.assertNotEqual(contrast["mean_difference"],tables["bootstrap"][0]["difference"])
    def test_numpy_global_rng_unchanged(self):
        import numpy as np
        before = np.random.get_state(); self.tables(); after = np.random.get_state()
        self.assertEqual(before[0],after[0]); np.testing.assert_array_equal(before[1],after[1]); self.assertEqual(before[2:],after[2:])
    def test_scenario_intervals_same_indices(self):
        import numpy as np
        table = self.tables()
        for row in table["scenario"]:
            vals = np.asarray([next(r for r in self.data["scenario_center"] if r["method"]==row["method"] and r["center_id"]==c and r["scenario"]==row["scenario"])["lifecycle_service_loss"] for c in CENTERS])
            low,high = np.quantile(vals[table["indices"]].mean(axis=1),[.025,.975],method="linear")
            self.assertEqual((row["ci_low"],row["ci_high"]),(float(low),float(high)))
    def test_leave_one_center_out_count(self):
        self.assertEqual(len(self.tables()["loo"]),4*3)
    def test_duplicate_center_rejected(self):
        self.data["center"].append(dict(self.data["center"][0]))
        with self.assertRaises(S.StatisticsIntegrityError): self.tables()
    def test_missing_center_rejected(self):
        self.data["center"].pop()
        with self.assertRaises(S.StatisticsIntegrityError): self.tables()
    def test_nonfinite_center_rejected(self):
        self.data["center"][0]["lifecycle_service_loss"] = float("inf")
        with self.assertRaises(S.StatisticsIntegrityError): self.tables()
    def test_missing_scenario_stratum_rejected(self):
        self.data["scenario_center"].pop()
        with self.assertRaises(S.StatisticsIntegrityError): self.tables()


class CostAndHistoryTests(unittest.TestCase):
    def test_complete_original_comparison_keeps_unfavorable_contrasts(self):
        old = [dict(method=method,mean_lifecycle_service_loss=10.-i,ci_low=1.,ci_high=20.) for i,method in enumerate(METHODS)]
        new = [dict(method=method,mean_lifecycle_service_loss=10.-i+(-1 if i==0 else 1),ci_low=1.,ci_high=20.) for i,method in enumerate(METHODS)]
        old_s = [dict(method=m,scenario=q,lifecycle_service_loss=1.) for m in METHODS for q in S.SCENARIOS]
        new_s = [dict(method=m,scenario=q,lifecycle_service_loss=2.) for m in METHODS for q in S.SCENARIOS]
        contrasts = [dict(comparison="P7.7 - "+m,mean_difference=7.-r["mean_lifecycle_service_loss"],ci_low=-3.,ci_high=1.) for m,r in zip(METHODS[:-1],new[:-1])]
        result = S.original_comparison_tables(new,new_s,contrasts,old,old_s)
        self.assertEqual((len(result["method"]),len(result["scenario"]),len(result["contrasts"])),(5,20,4))
        self.assertEqual(result["method"][0]["corrected_minus_original"],-1.)
        self.assertEqual(result["method"][-1]["corrected_minus_original"],1.)
        self.assertFalse(result["contrasts"][0]["new_heldout_is_unseen"])
    def test_runtime_counters_and_timers_separate(self):
        data = S.execution_cost_tables(synthetic_rows(),**CONTRACT)
        self.assertEqual(len(data["trajectory"]),60); self.assertEqual(len(data["method"]),5)
        proposed = next(r for r in data["method"] if r["method"]=="P7.7")
        self.assertEqual(proposed["ri_search_updates_charged_total_recorded"],1800.)
        self.assertEqual(proposed["decision_runtime_actual_s_total_recorded"],6.)
        self.assertEqual(proposed["decision_runtime_standalone_estimate_s_total_recorded"],12.)
    def test_runtime_negative_rejected(self):
        rows = synthetic_rows(); rows[0]["decision_runtime_actual_s"] = -1.
        with self.assertRaises(S.StatisticsIntegrityError): S.execution_cost_tables(rows,**CONTRACT)
    def test_runtime_missing_rejected(self):
        rows = synthetic_rows(); del rows[0]["source_cache_hits"]
        with self.assertRaises(S.StatisticsIntegrityError): S.execution_cost_tables(rows,**CONTRACT)
    def test_runtime_invalid_boolean_rejected(self):
        rows = synthetic_rows(); rows[0]["shared_parent_cache_hit"] = "maybe"
        with self.assertRaises(S.StatisticsIntegrityError): S.execution_cost_tables(rows,**CONTRACT)
    def test_runtime_duplicate_stage_rejected(self):
        rows = synthetic_rows(); rows.append(dict(rows[0]))
        with self.assertRaises(S.StatisticsIntegrityError): S.execution_cost_tables(rows,**CONTRACT)
    def history(self,attempts): return S.validate_phase_attempts("initial",attempts,[{"center_id":7,"seed":11},{"center_id":9,"seed":11}],task_fields=("center_id","seed"))
    def attempt(self,num,tasks,success=True): return dict(attempt_id=f"A_INITIAL_{num:04d}",tasks=[{"center_id":c,"seed":11} for c in tasks],success=success,failure_preserved=not success,end_integrity_pass=success)
    def test_failed_attempt_retry_preserved(self):
        result = self.history([self.attempt(1,[7,9],False),self.attempt(2,[9])]); self.assertEqual(result["failed_attempts_preserved"],1)
    def test_final_failed_attempt_rejected(self):
        with self.assertRaises(S.StatisticsIntegrityError): self.history([self.attempt(1,[7,9],False)])
    def test_unrequested_task_rejected(self):
        with self.assertRaises(S.StatisticsIntegrityError): self.history([self.attempt(1,[7])])
    def test_outside_task_rejected(self):
        with self.assertRaises(S.StatisticsIntegrityError): self.history([self.attempt(1,[7,9,13])])
    def test_duplicate_within_attempt_rejected(self):
        with self.assertRaises(S.StatisticsIntegrityError): self.history([self.attempt(1,[7,7,9])])
    def test_missing_end_integrity_rejected(self):
        item = self.attempt(1,[7,9]); item["end_integrity_pass"] = False
        with self.assertRaises(S.StatisticsIntegrityError): self.history([item])


class GuardAndStaticTests(unittest.TestCase):
    def contract(self,path):
        repo = ROOT.parents[2]
        return dict(bound={str(Path(path).resolve()).casefold():"a"*64},repo=repo,statistics_root=ROOT,
                    executor_root=repo/"verification/paper3_canonical_inputs/replication_executor_batch20_env_v3",
                    site_root=SELECTED_SITE,stdlib_root=Path(sys.base_prefix)/"Lib")
    def test_statistics_source_allowed(self):
        path = ROOT/"statistics.py"; self.assertTrue(G.allowed_module_origin("stats",path,**self.contract(path)))
    def test_original_model_import_forbidden(self):
        path = ROOT.parents[2]/"core/p7.py"; self.assertFalse(G.allowed_module_origin("core.p7",path,**self.contract(path)))
    def test_executor_adapter_import_forbidden(self):
        path = ROOT.parent/"replication_executor_batch20_env_v3/science_adapter.py"; self.assertFalse(G.allowed_module_origin("adapter",path,**self.contract(path)))
    def test_torch_import_forbidden(self):
        path = SELECTED_SITE/"torch/__init__.py"; self.assertFalse(G.allowed_module_origin("torch",path,**self.contract(path)))
    def test_pandas_import_forbidden(self):
        path = SELECTED_SITE/"pandas/__init__.py"; self.assertFalse(G.allowed_module_origin("pandas",path,**self.contract(path)))
    def test_numpy_bound_import_allowed(self):
        path = SELECTED_SITE/"numpy/__init__.py"; self.assertTrue(G.allowed_module_origin("numpy",path,**self.contract(path)))
    def test_selected_numpy_site_inside_repository(self):
        self.assertTrue(ROOT.parents[2] in SELECTED_SITE.parents)
        path = SELECTED_SITE/"numpy/_core/_multiarray_umath.pyd"
        self.assertTrue(G.allowed_module_origin("numpy._core._multiarray_umath",path,**self.contract(path)))
    def test_repository_numpy_source_unbound_rejected(self):
        path = SELECTED_SITE/"numpy/__init__.py"; contract = self.contract(path); contract["bound"] = {}
        self.assertFalse(G.allowed_module_origin("numpy",path,**contract))
    def test_original_project_cannot_use_numpy_module_name(self):
        path = ROOT.parents[2]/"core/p7.py"
        self.assertFalse(G.allowed_module_origin("numpy.core.p7",path,**self.contract(path)))
    def test_other_site_package_cannot_use_numpy_module_name(self):
        path = SELECTED_SITE/"pandas/__init__.py"
        self.assertFalse(G.allowed_module_origin("numpy.alias",path,**self.contract(path)))
    def test_other_bound_repository_site_packages_rejected(self):
        for module in ("river","sklearn","psutil"):
            path = SELECTED_SITE/module/"__init__.py"
            self.assertFalse(G.allowed_module_origin(module,path,**self.contract(path)))
    def test_unbound_import_rejected(self):
        path = ROOT/"statistics.py"; contract = self.contract(path); contract["bound"] = {}
        self.assertFalse(G.allowed_module_origin("stats",path,**contract))
    def test_no_project_models_or_generators_imported(self):
        self.assertFalse(any(name=="torch" or name.startswith(("torch.","core.","imported.","scripts.")) for name in sys.modules))
    def test_top_level_imports_stdlib_only(self):
        for filename in ("statistics.py","runtime_guard.py","run_statistics.py"):
            tree = ast.parse((ROOT/filename).read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(node,ast.Import): self.assertTrue(all(alias.name.split(".")[0] in sys.stdlib_module_names for alias in node.names))
                elif isinstance(node,ast.ImportFrom): self.assertIn((node.module or "").split(".")[0],sys.stdlib_module_names)
    def test_real_entry_wrong_root_rejected_before_outcomes(self):
        with self.assertRaises(S.StatisticsIntegrityError): S.validate_statistics_gate(ROOT,ROOT,expected_manifest_digest="a"*64)
    def test_dedicated_process_real_numpy_import_and_read_rejection(self):
        command = [sys.executable,"-I","-S","-B","-X",f"pycache_prefix={ROOT/'_never_created_guard_pycache'}",
                   str(Path(__file__).resolve()),"--site-packages",str(SELECTED_SITE),"--guard-probe"]
        completed = subprocess.run(command,capture_output=True,text=True,check=False)
        self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)
        proof = json.loads(completed.stdout.strip())
        self.assertTrue(proof["real_numpy_import_pass"] and proof["torch_import_rejected"] and proof["unbound_read_rejected"])
        self.assertTrue(proof["selected_site_inside_repository"])


def guard_probe(site):
    """Real NumPy import under the guard, using only synthetic provenance metadata.

    The repository path matches the selected environment's real nesting, but
    its proof inventories are synthetic. No original/outcome material is read;
    only actual installed NumPy/stdlib and new statistics bytes are SHA-bound.
    """
    bound = {}
    standard = Path(sys.base_prefix)/"Lib"
    for folder in (standard,Path(sys.base_prefix)/"DLLs",site/"numpy",site/"numpy.libs"):
        if not folder.exists(): continue
        for directory,dirs,names in __import__("os").walk(folder):
            dirs[:] = [name for name in dirs if name not in {"site-packages","__pycache__"}]
            for name in names:
                path = Path(directory)/name
                if path.suffix.lower() in {".py",".pyd",".dll"}: bound[str(path.resolve())] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in ROOT.rglob("*.py"): bound[str(path.resolve())] = hashlib.sha256(path.read_bytes()).hexdigest()
    for module in tuple(sys.modules.values()):
        filename = getattr(module,"__file__",None)
        if filename and not filename.startswith("<"):
            path = Path(filename).resolve(); bound[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    repository = ROOT.parents[2]
    if repository not in site.parents:
        raise RuntimeError("Guard probe requires the reviewed site inside the repository")
    class FixtureProvenance:
        @staticmethod
        def regular_path(path,**kwargs): return Path(path).resolve()
        @staticmethod
        def checked_path(root,relative,**kwargs): return (Path(root)/relative).resolve()
        @staticmethod
        def read_json(path): return {"files":{}}
        @staticmethod
        def file_sha256(path):
            path = Path(path).resolve()
            # Actual repo proof files are intentionally never opened by this
            # synthetic fixture, even when an inert proof path happens to exist.
            return hashlib.sha256(path.read_bytes()).hexdigest() if str(path) in bound else hashlib.sha256(b"SYNTHETIC_METADATA_ONLY").hexdigest()
    manifest = {"paths":{"repo":str(repository),"executor_root":str(repository/"_synthetic_executor_never_created"),"input_run":str(repository/"_synthetic_input_never_created"),"results_root":str(repository/"_synthetic_results_never_created")},
        "environment":{"bound_files_sha256":bound,"site_packages_root":str(site)},"critical_files_sha256":{},
        "original_python_dependency_sha256":{},"original_protected_snapshot":{},"executor_sha256":{},"input_files_sha256":{}}
    G.install_statistics_import_guard(manifest,{},FixtureProvenance)
    import numpy as np
    actual = bool(np.asarray([1.,2.,3.]).sum()==6.)
    denied = False
    try: __import__("torch")
    except G.StatisticsGuardError: denied = True
    rejected = False
    try:
        with (ROOT/"definitely_unbound_read_probe.txt").open("rb") as stream: stream.read()
    except G.StatisticsGuardError: rejected = True
    if not actual or not denied or not rejected: raise RuntimeError("guard probe did not enforce contract")
    print(json.dumps({"real_numpy_import_pass":actual,"torch_import_rejected":denied,"unbound_read_rejected":rejected,
                       "selected_site_inside_repository":True,"real_outcomes_read":False,"models_executed":False},sort_keys=True),flush=True)
    return 0


def main():
    global SELECTED_SITE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-packages",required=True)
    parser.add_argument("--evidence",type=Path)
    parser.add_argument("--guard-probe",action="store_true")
    args = parser.parse_args()
    site = Path(args.site_packages).resolve()
    allowed_sites = {Path(sys.prefix)/"Lib/site-packages",Path(sys.base_prefix)/"Lib/site-packages"}
    executable = Path(sys.executable).resolve()
    if executable.parent.name.casefold()=="scripts" and (executable.parent.parent/"pyvenv.cfg").is_file():
        allowed_sites.add(executable.parent.parent/"Lib/site-packages")
    if site not in allowed_sites:
        raise RuntimeError("Synthetic tests require current interpreter site-packages only")
    SELECTED_SITE = site
    sys.path.append(str(site))
    if args.guard_probe: return guard_probe(site)
    started = datetime.now(timezone.utc).isoformat()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    import numpy as np
    receipt = {"schema":"paper3-statistics-independent-synthetic-tests-v1","started_utc":started,
        "finished_utc":datetime.now(timezone.utc).isoformat(),"tests":result.testsRun,"failures":len(result.failures),
        "errors":len(result.errors),"all_pass":result.wasSuccessful(),"python_executable":sys.executable,
        "python_executable_sha256":hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
        "site_packages_root":str(site),"numpy_version":np.__version__,
        "real_outcomes_read":False,"project_models_or_generators_executed":False,
        "implementation_sha256":{path.relative_to(ROOT).as_posix():hashlib.sha256(path.read_bytes()).hexdigest() for path in ROOT.rglob("*.py")}}
    if args.evidence:
        path = args.evidence.resolve()
        if path.parent!=ROOT: raise RuntimeError("Test evidence must remain in new statistics directory")
        with path.open("x",encoding="utf-8",newline="\n") as stream: json.dump(receipt,stream,sort_keys=True,indent=2); stream.write("\n")
    print(json.dumps(receipt,sort_keys=True),flush=True)
    return 0 if result.wasSuccessful() else 1


if __name__=="__main__": raise SystemExit(main())
