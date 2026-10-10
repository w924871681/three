"""Authorized import-only phase/guard check; no project or model execution."""
from __future__ import annotations

import argparse
import copy
import importlib.abc
import json
import os
from pathlib import Path
import sys
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
RESULTS=REPO/"results/p7_7_integrity_replication_batch20_env_v3"
PREDECESSOR=REPO/"results/p7_7_integrity_replication_batch20_env_v2/provenance_manifest.json"


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--attempt",type=int,required=True)
    args=parser.parse_args()
    if args.attempt<1:raise RuntimeError("positive exclusive attempt required")
    sys.path.insert(0,str(ROOT))
    import provenance as p
    output=p.regular_path(RESULTS/"stage_c_tests/sklearn_import_transition_probe"/f"attempt{args.attempt:03d}",must_exist=False)
    if output.exists():raise RuntimeError("refusing to overwrite import-only probe evidence")
    cache=output/"_never_created_pycache"
    if not(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and
           sys.pycache_prefix and p.regular_path(sys.pycache_prefix,must_exist=False)==cache and not cache.exists()):
        raise RuntimeError("probe requires -I -S -B and its exclusive nonexistent bytecode prefix")
    prior=p.read_json(PREDECESSOR)
    if prior["manifest_digest"]!="468ee2a0a174ba17c65d98e87afeb521aca3cab77c611d31e60d9f2f4bc0aba8":
        raise RuntimeError("frozen predecessor manifest differs")
    start_sources={path.relative_to(ROOT).as_posix():p.file_sha256(path) for path in sorted(ROOT.rglob("*.py"))}
    environment=copy.deepcopy(prior["environment"])
    raw=p._model_runtime_environment()
    if {name:raw[name] for name in prior["environment"]["model_runtime_environment"]}!=prior["environment"]["model_runtime_environment"]:
        raise RuntimeError("raw independent environment differs from the frozen predecessor")
    if raw["KMP_INIT_AT_FORK"] is not None:raise RuntimeError("probe expected the independently observed unset initializer flag")
    environment["model_runtime_environment"]=raw
    environment["model_runtime_environment_digest"]=p.canonical_hash(raw)
    manifest={"schema":"paper3-independent-import-only-transition-check-binding-v1",
              "paths":{**prior["paths"],"executor_root":str(ROOT),"results_root":str(RESULTS)},
              "environment":environment,"executor_sha256":start_sources,
              "original_python_dependency_sha256":prior["original_python_dependency_sha256"],
              "predecessor_manifest_digest":prior["manifest_digest"],"predecessor_manifest_file_sha256":p.file_sha256(PREDECESSOR),
              "input_bundle_digest_reference_only":prior["input_bundle_digest"],"input_arrays_read":False}
    manifest["manifest_digest"]=p.canonical_hash(manifest)
    output.mkdir(parents=True,exist_ok=False)
    started=datetime.now(timezone.utc).isoformat()
    p.install_write_guard(RESULTS)
    p.install_generator_guard(REPO)
    p.install_model_import_guard(manifest)
    denied={"core","imported","scripts","torch","river","verification"}
    class ImportOnly(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            if fullname.split(".")[0] in denied:raise RuntimeError("project/model import forbidden in package-only probe: "+fullname)
            return None
    sys.meta_path.insert(0,ImportOnly())
    sys.path.append(environment["site_packages_root"])
    token=p.begin_scientific_import_transition(manifest)
    print("IMPORT_ONLY_RAW_BOUND",flush=True)
    import sklearn
    proof=p.complete_scientific_import_transition(manifest,token)
    p._verify_model_runtime_environment(environment)
    p.check_loaded_modules(manifest)
    expected=dict(raw)
    expected.update(KMP_DUPLICATE_LIB_OK="True",KMP_INIT_AT_FORK="FALSE")
    if p._model_runtime_environment()!=expected:raise RuntimeError("unapproved package import transition")
    if any(name.split(".")[0] in denied for name in sys.modules):raise RuntimeError("forbidden real project/model package loaded")
    end_sources={path.relative_to(ROOT).as_posix():p.file_sha256(path) for path in sorted(ROOT.rglob("*.py"))}
    if start_sources!=end_sources:raise RuntimeError("probe source changed during execution")
    if p.file_sha256(PREDECESSOR)!=manifest["predecessor_manifest_file_sha256"]:raise RuntimeError("predecessor manifest changed")
    receipt={"schema":"paper3-actual-sklearn-import-transition-probe-v1","status":"PASS",
             "started_utc":started,"finished_utc":datetime.now(timezone.utc).isoformat(),
             "manifest_binding_digest":manifest["manifest_digest"],"manifest_binding":manifest,
             "scientific_import_transition":proof,"implementation_sha256":end_sources,
             "implementation_unchanged":True,"python_executable":sys.executable,
             "python_executable_sha256":p.file_sha256(sys.executable),"sklearn_version":sklearn.__version__,
             "project_or_model_imported":False,"input_arrays_loaded":False,"checkpoints_deserialized":False,
             "model_or_optimizer_called":False,"generation_performed":False,"seeds_set":False,"statistics_performed":False,
             "original_results_changed_by_probe":False,"verifier_environment_mutation_performed":False,
             "full_dependency_environment_reverified":False,"scope":"ACTUAL_SOURCE_BOUND_IMPORT_DEFAULT_OBSERVATION_ONLY"}
    publication=p.publish_json(RESULTS,(output/"receipt.json").relative_to(RESULTS).as_posix(),receipt)
    print(json.dumps({"status":"PASS","receipt":publication,"observed_writer_events":proof["observed_writer_events"]},sort_keys=True),flush=True)
    return 0


if __name__=="__main__":raise SystemExit(main())
