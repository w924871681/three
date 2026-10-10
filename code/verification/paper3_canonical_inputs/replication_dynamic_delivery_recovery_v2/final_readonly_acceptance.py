"""Independent, strictly read-only acceptance of the finished V2 delivery.

This file is deliberately outside pipeline.OWN and the production import graph.
It imports only the standard library, never starts a process, never writes a file,
never imports a project module, and never computes/recomputes a model endpoint,
bootstrap, confidence interval, or model output.  Root may save stdout separately
to a NEW exclusive observation file.  Run only after the producer has finished.

Usage:
  <metadata-python> -I -S -B final_readonly_acceptance.py \
    --expected-plan-sha256 <actual finalized V2 plan SHA> \
    --supervisor-exit-observation <root-owned actual exit observation JSON> \
    --supervisor-exit-sha256 <its actual SHA>

The optional supervisor observation is separate because a producer's finish.json
cannot prove its own OS exit.  Without it, otherwise successful checks return
PARTIAL (exit 2), with that precise remaining uncertainty.
"""
from __future__ import annotations

import argparse
import ast
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import sys
import zipfile


HERE = Path(__file__).resolve().parent
BASE = HERE.parent
REPO = BASE.parents[1]
RESULTS = REPO / "results/p7_7_integrity_replication_batch20_env_v3"
STATS = RESULTS / "statistics_batch20_env_v3"
PLAN = HERE / "RECOVERY_DELIVERY_PLAN_002.json"
PLAN_SHA = "174c04348357f05537a034db69d9f2c5941b4f5ef700783ee02087f0cb5deba5"
SUPERVISOR_IDENTITY_SHA = "1b24658842175caaba27a64cb6fc4178e0875da5b4bc1a99901ae0378fa0ea18"
SUPERVISOR_LAUNCH_SHA = "bf9551297e1ba857f2d48cb720567042cce726ad1628d5acbac54f97f5b28971"
SUPERVISOR_CREATION_SHA = "c70eb875f81c0f2e694f705845650dbcf5507c2f04d61daeadde729d3c62112c"
RECORD = HERE / "sequence002"
CONTROL = HERE / "supervisor002"
ERRATUM_ROOT = BASE / "replication_dynamic_delivery_erratum_v1"
ERRATUM_PLAN = ERRATUM_ROOT / "ERRATUM_RECOVERY_PLAN_002.json"
ERRATUM_RECORD = ERRATUM_ROOT / "erratum_recovery002"
ERRATUM_PROOF = ERRATUM_ROOT / "SMOKE_COUNT_ERRATUM_SYNTHETIC_TEST_RESULTS_ATTEMPT004.json"
ERRATUM_PROOF_SHA = "8c7ffcf50294c0f894be3412beeafe132562857ca7abf23893d82e246e34f9c6"
ERRATUM_PINS = {str(ERRATUM_ROOT / name): digest for name, digest in {
    "metadata_erratum.py": "3461322dd57af084d46a98d6cdb66abca473d006902fb90e37694013d92bebce",
    "erratum_watch.py": "cdf0d78d2930b6d7c2211b0336378ce226bb6ea39a39be0d6377cd343c8fbcd2",
    "test_metadata_erratum.py": "0cc55daa5c4a2334cf9ff83ef178b7374aa6a12d62804618bd7575d60895d29c",
    "run_erratum_tests.py": "1ee51a7021c9c2eb8b5a1f463f55172e153159fcc67f235e5fa3f271cba6ceb8"}.items()}
MANIFEST = "7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea"
MANIFEST_FILE_SHA = "c9277ed25b9c4e6df0b2ecfffeeefa3fdaa087ba4f326de828513402d5d20076"
F1 = "ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228"
F50 = "f50fa7c8e6abd916124d423ad2b5950df2a7c631d02403eaf8e1cc5736f06ee8"
CERT_SHA = "027cce63906b5879d69c35f9d95eddd5e3776189a2b4a1f60628733e773bff58"
GATE_SHA = "a33555e7f6083229aff520fe6e0a8f6ad11b2ef468cda3f8929be4cbe9240a97"
INITIAL_SHA = "18b329d5468d85961e28f24a1f45df9b2191530a9b26244642dbf6d2304e19dc"
CERT = BASE / "replication_dynamic_delivery_recovery_v1/sequence001/DYNAMIC_FULL_INTEGRITY_CERTIFICATE.json"
REPORTS = ("EXECUTION_SUMMARY.md", "INPUT_PARITY_AUDIT.md", "EXPERIMENT_INTEGRITY_AUDIT.md",
           "CORRECTED_FINAL_STATISTICS.md", "ORIGINAL_VS_REPLICATION_COMPARISON.md", "SCIENTIFIC_FREEZE_DECISION.md")
DRAFT = "PAPER3_FINAL_REPLICATION_HANDOFF_DRAFT.md"
ROOT_HANDOFF = "PAPER3_FINAL_REPLICATION_HANDOFF.md"
METHODS = {"B0": "B0_Frozen_ratio10", "B1": "B1_AlwaysMaintainP50_ratio10", "B2": "B2_RAVM_ratio10",
           "B8": "B8_AlwaysOpen_ratio10", "P7.7": "P7_7_RECOVERABILITY_GUIDED_ratio10_grid33"}
SCENARIOS = ("C0", "C1", "C3", "C4")
INPUT_FIELDS = ("scenario_hash", "D_upd_hash", "D_assess_hash", "D_srv_hash", "center_type",
                "deployment_tier", "deployment_filter_hash", "bank_hash", "update_end_ts",
                "decision_ts", "scenario_role", "initial_state_hash")
EXPECTED_COUNTS = {"raw_trajectories": 1200, "five_method_groups": 240, "stages": 28800,
                   "center_method_rows": 100, "scenario_center_rows": 400, "paired_bootstrap_rows": 16000,
                   "method_bootstrap_rows": 20000, "loo_rows": 80}
CSV_ROWS = {"final_metrics_by_trajectory.csv": 1200, "final_metrics_by_center.csv": 100,
            "final_metrics_by_scenario_center.csv": 400, "final_metrics_by_method.csv": 5,
            "final_metrics_by_scenario.csv": 20, "final_paired_contrasts.csv": 4,
            "final_method_bootstrap.csv": 20000, "final_paired_bootstrap.csv": 16000,
            "final_loo.csv": 80, "final_decision_diagnostics.csv": 4,
            "final_execution_cost_by_trajectory.csv": 1200, "final_execution_cost_by_method.csv": 5,
            "original_vs_corrected_by_method.csv": 5, "original_vs_corrected_by_scenario.csv": 20,
            "original_vs_corrected_observed_contrasts.csv": 4}


class AcceptanceError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise AcceptanceError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key: " + str(path))
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(AcceptanceError("nonfinite JSON: " + value)))


def exact(value, expected, label):
    require(isinstance(value, dict), label + " is not an object")
    for key, wanted in expected.items():
        got = value.get(key)
        if isinstance(wanted, bool):
            require(got is wanted, label + " boolean differs: " + key)
        elif type(wanted) is int:
            require(type(got) is int and got == wanted, label + " integer differs: " + key)
        else:
            require(got == wanted, label + " differs: " + key)


def digest_string(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def safe_relative(root, relative):
    require(isinstance(relative, str) and "\\" not in relative, "noncanonical relative path")
    item = PurePosixPath(relative)
    require(not item.is_absolute() and item.parts and ".." not in item.parts and ":" not in relative,
            "unsafe relative path: " + relative)
    path = Path(root).joinpath(*item.parts)
    require(path.resolve().is_relative_to(Path(root).resolve()), "relative path escapes root")
    return path


class Auditor:
    def __init__(self):
        self.expected = {}
        self.signatures = {}
        self.parent_checked = set()
        self.bytes_hashed = 0
        self.zipped_files_checked = 0
        self.external_allowed = set()
        self.checks = {}

    def path(self, path):
        path = Path(path)
        require(path.is_absolute(), "absolute evidence path required")
        lexical = path.absolute()
        require(".." not in lexical.parts, "parent traversal in evidence path")
        resolved = lexical.resolve()
        require(resolved.is_relative_to(REPO) or str(resolved).casefold() in self.external_allowed,
                "unapproved external evidence path: " + str(path))
        for parent in (lexical, *lexical.parents):
            key = str(parent).casefold()
            if key in self.parent_checked:
                break
            require(not parent.is_symlink(), "symlink evidence rejected: " + str(parent))
            if parent.exists():
                require(not getattr(parent.lstat(), "st_file_attributes", 0) & 0x400,
                        "reparse evidence rejected: " + str(parent))
            self.parent_checked.add(key)
        require(resolved.is_file(), "required evidence file missing: " + str(resolved))
        return resolved

    @staticmethod
    def signature(path):
        value = path.stat()
        return value.st_size, value.st_mtime_ns, value.st_ino

    def sha(self, path):
        path = self.path(path)
        key = str(path)
        signature = self.signature(path)
        if key in self.signatures:
            require(self.signatures[key] == signature, "evidence changed during acceptance: " + key)
            return self.expected[key]
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1048576), b""):
                self.bytes_hashed += len(chunk)
                h.update(chunk)
        require(self.signature(path) == signature, "evidence changed while hashing: " + key)
        self.signatures[key] = signature
        self.expected[key] = h.hexdigest()
        return h.hexdigest()

    def bound(self, path, expected):
        require(digest_string(expected), "invalid expected SHA: " + str(path))
        actual = self.sha(path)
        require(actual == expected, "SHA mismatch: " + str(path))
        return self.path(path)

    def bound_json(self, path, expected):
        path = self.bound(path, expected)
        value = read(path)
        require(self.signature(path) == self.signatures[str(path)], "JSON changed while read")
        return value

    def binding_map(self, mapping):
        require(isinstance(mapping, dict) and mapping, "empty or invalid SHA inventory")
        for filename, expected in mapping.items():
            self.bound(filename, expected)
        return len(mapping)

    def inventory(self, root):
        root = Path(root).resolve()
        require(root.is_relative_to(REPO / "handoffs") and root.is_dir(), "invalid package root")
        result = {}
        for path in sorted(root.rglob("*")):
            require(not path.is_symlink() and not getattr(path.lstat(), "st_file_attributes", 0) & 0x400,
                    "package reparse entry rejected: " + str(path))
            if path.is_file():
                result[path.relative_to(root).as_posix()] = self.sha(path)
        return result

    def package(self, root, name, exclusions, schema):
        root = Path(root).resolve()
        path = root / name
        self.sha(path)
        value = read(path)
        exact(value, {"schema": schema, "status": "COMPLETED"}, name)
        expected = value["package_files_sha256"]
        require(isinstance(expected, dict) and expected, "empty package inventory")
        for relative, digest in expected.items():
            self.bound(safe_relative(root, relative), digest)
        actual = self.inventory(root)
        require({n: h for n, h in actual.items() if n not in exclusions} == expected,
                "package file set/SHA differs: " + str(root))
        return value, actual

    def zip(self, path, expected_sha, inventory):
        path = self.bound(path, expected_sha)
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            require(len(names) == len(set(names)) and set(names) == set(inventory), "ZIP inventory differs")
            for item in archive.infolist():
                require(not item.is_dir() and not item.flag_bits & 1, "directory/encrypted ZIP entry prohibited")
                require(not PurePosixPath(item.filename).is_absolute() and ".." not in PurePosixPath(item.filename).parts,
                        "unsafe ZIP entry")
                h = hashlib.sha256()
                with archive.open(item) as stream:
                    for chunk in iter(lambda: stream.read(1048576), b""):
                        h.update(chunk)
                require(h.hexdigest() == inventory[item.filename], "ZIP member SHA differs: " + item.filename)
                self.zipped_files_checked += 1
        require(self.signature(path) == self.signatures[str(path)], "ZIP changed while read")

    def stable(self):
        for filename, signature in self.signatures.items():
            require(self.signature(Path(filename)) == signature, "evidence changed before audit end: " + filename)


def stem(task):
    return f"{task['config_id']}_{task['center_id']}_{task['seed']}_{task['scenario']}"


def check_raw(a, gate, manifest):
    expected_groups = {f"{c}/{seed}/{scenario}" for c in range(33000, 33020)
        for seed in (7311, 7312, 7313) for scenario in SCENARIOS}
    require(set(gate["groups"]) == expected_groups, "group domain differs")
    expected_files = set()
    stages = 0
    for group_id, group in gate["groups"].items():
        c, seed, scenario = group_id.split("/")
        exact(group, {"five_methods": True, "all_24_stage_input_fields_equal": True}, "group")
        require(set(group["receipt_sha256"]) == set(METHODS), "group does not have exact five methods")
        reference = None
        reference_rows = None
        for method, config in METHODS.items():
            task = {"center_id": int(c), "seed": int(seed), "scenario": scenario, "method": method, "config_id": config}
            name = stem(task)
            csv_path = RESULTS / "raw" / (name + ".csv")
            receipt_path = RESULTS / "raw" / (name + ".integrity.json")
            expected_files.update((csv_path.name, receipt_path.name))
            receipt = a.bound_json(receipt_path, group["receipt_sha256"][method])
            exact(receipt, {"schema": "paper3-batch20-replication-trajectory-receipt-v1", "task": task,
                "valid": True, "trajectory_rows": 24, "manifest_digest": MANIFEST, "input_bundle_digest": F1,
                "performance_based_continuation": False, "full_24_stage_input_parity_checked": True,
                "future_online_access_violation_count": 0, "statistics_executed": False}, "raw receipt")
            # scenario_hash is an original CSV field, not a receipt field.
            for key in ("initial_state_hash", "deployment_tier", "deployment_filter_hash", "bank_hash"):
                require(receipt.get(key) == group.get(key), "paired receipt field differs: " + key)
            hashes = receipt["stage_input_hashes"]
            require(len(hashes) == 24 and [item["stage"] for item in hashes] == list(range(1, 25)), "stage hash domain differs")
            require(reference is None or hashes == reference, "five-method stage input hashes differ")
            reference = hashes
            a.bound(csv_path, receipt["output_hash"])
            if "audit_sha256" in receipt:
                require(receipt["audit_sha256"] == receipt["audit_hash"], "receipt audit alias differs")
            for path_key, sha_key in (("audit_relative", "audit_hash"), ("rng_relative", "rng_file_sha256"),
                                     ("attempt_csv_relative", "attempt_csv_hash"), ("runtime_receipt_path", "runtime_receipt_sha256")):
                a.bound(safe_relative(RESULTS, receipt[path_key]), receipt[sha_key])
            with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)), "duplicate raw CSV header")
                count = 0
                input_rows = []
                for count, row in enumerate(reader, 1):
                    require(count <= 24 and None not in row and None not in row.values(), "raw CSV stage/width differs")
                    for key in ("config_id", "method", "center_id", "seed", "scenario"):
                        require(row.get(key) == str(task[key]), "CSV task differs")
                    require(int(row["stage"]) == count, "CSV stage index differs")
                    for key in ("D_upd_hash", "D_assess_hash", "D_srv_hash"):
                        require(row.get(key) == hashes[count - 1][key], "CSV role input hash differs")
                    for key in ("initial_state_hash", "scenario_hash", "deployment_tier", "deployment_filter_hash", "bank_hash"):
                        require(row.get(key) == str(group[key]), "CSV paired field differs: " + key)
                    require(set(INPUT_FIELDS) <= set(row), "original pairing column missing")
                    input_rows.append(tuple(row[key] for key in INPUT_FIELDS))
                require(count == 24, "CSV is not a full trajectory")
                require(reference_rows is None or input_rows == reference_rows, "original 12-field stage pairing differs")
                reference_rows = input_rows
                stages += count
    raw = RESULTS / "raw"
    require(all(path.is_file() for path in raw.iterdir()), "unexpected raw publication directory")
    require({path.name for path in raw.iterdir() if path.is_file()} == expected_files, "raw publication file inventory differs")
    require(stages == 28800, "raw total stage count differs")
    a.checks["raw_matrix"] = {"trajectories": 1200, "paired_groups": 240, "stages": stages,
        "all_24_stage_input_hashes_freshly_compared": True, "loss_values_not_used_for_selection_or_recomputed": True}


def check_statistics(a, manifest):
    receipt_path = STATS / "statistics_execution_receipt.json"
    a.sha(receipt_path)
    receipt = read(receipt_path)
    exact(receipt, {"schema": "paper3-statistics-execution-receipt-v1", "status": "COMPLETED", "exit_code": 0,
        "replication_manifest_digest": MANIFEST, "originals_unchanged": True, "models_or_generators_executed": False,
        "new_output_only": True, "joint_resampling_verified": True}, "statistics receipt")
    stats = a.bound_json(STATS / "statistics_manifest.json", receipt["statistics_manifest_sha256"])
    exact(stats, {"schema": "paper3-joint-center-statistics-manifest-v1", "replication_manifest_digest": MANIFEST,
                  "input_bundle_digest": F1, "counts": EXPECTED_COUNTS}, "statistics manifest")
    exact(stats["protocol"], {"resampling_unit": "center", "centers": list(range(33000, 33020)),
        "bootstrap_resamples": 4000, "bootstrap_seed": 2904, "one_joint_index_matrix_for_all_methods_contrasts_scenarios": True,
        "interval": "percentile 95%, NumPy method=linear", "historical_draw_sequence_reproduced": False,
        "observed_point_estimates_from_original_center_means": True, "new_unseen_heldout_claimed": False,
        "no_outcome_based_selection": True, "no_original_records_reused": True, "no_exclusions": True,
        "winner_ranking": False, "models_or_generators_executed": False}, "statistics protocol")
    outputs = stats["outputs_sha256"]
    require(outputs == receipt["outputs_sha256"] and set(outputs) == set(CSV_ROWS) | {"joint_center_resample_indices.npy"},
            "statistics output inventory differs")
    for relative, digest in outputs.items():
        a.bound(safe_relative(STATS, relative), digest)
    for name, wanted in CSV_ROWS.items():
        with (STATS / name).open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader)
            require(header and len(header) == len(set(header)), "invalid statistics CSV header")
            count = 0
            for count, row in enumerate(reader, 1):
                require(len(row) == len(header), "statistics CSV width differs: " + name)
            require(count == wanted, "statistics CSV row count differs: " + name)
    with (STATS / "joint_center_resample_indices.npy").open("rb") as stream:
        require(stream.read(6) == b"\x93NUMPY", "joint matrix is not an NPY file")
        major, minor = stream.read(2)
        require(major in (1, 2, 3), "NPY version differs")
        size = struct.unpack("<H" if major == 1 else "<I", stream.read(2 if major == 1 else 4))[0]
        header = ast.literal_eval(stream.read(size).decode("utf-8" if major == 3 else "latin1").strip())
        require(header == {"descr": "<i8", "fortran_order": False, "shape": (4000, 20)}, "joint matrix shape/dtype differs")
        require(len(stream.read()) == 4000 * 20 * 8, "joint matrix payload size differs")
    count = a.binding_map(stats["input_bindings_sha256"])
    for filename, digest in stats["implementation_files_sha256"].items():
        a.bound(filename, digest)
    a.checks["statistics"] = {"completed": True, "counts": stats["counts"], "input_bindings_verified": count,
        "outputs_verified": len(outputs), "joint_center_protocol": True, "statistics_recomputed": False}
    return stats, receipt


def check_publication(a, publication, old_sha, new_sha):
    value_path = publication / "PUBLICATION_RECEIPT.json"
    a.sha(value_path)
    exact(read(value_path), {"status": "PUBLISHED_VERIFIED_SAVED_DRAFT", "previous_sha256": old_sha,
        "new_sha256": new_sha, "all_prior_bytes_archived": True}, "root publication")
    a.bound(publication / "PREVIOUS_ROOT_HANDOFF_UNMODIFIED.md", old_sha)
    a.bound(publication / ROOT_HANDOFF, new_sha)


def check_erratum_proof(a, plan):
    """Source-bound synthetic certification, without importing its producer."""
    proof = a.bound_json(ERRATUM_PROOF, ERRATUM_PROOF_SHA)
    exact(proof, {"schema": "paper3-smoke-count-erratum-synthetic-proof-v1", "all_pass": True,
        "failures": 0, "errors": 0, "skipped": 0, "tests_run": 47,
        "actual_models_statistics_publication_or_process_control": False,
        "real_outcomes_read": False, "implementation_sha256": ERRATUM_PINS}, "erratum proof004")
    a.binding_map(ERRATUM_PINS)
    expected_v1 = {Path(filename).name: digest for filename, digest in plan["implementation_sha256"].items()}
    require(proof["v1_source_sha256"] == expected_v1, "erratum proof V1 source map differs")
    contract = a.bound_json(plan["contract_path"], plan["contract_sha256"])
    require(proof["scheduler_source_sha256"] == contract["sidecar_sources"], "erratum proof scheduler source map differs")
    a.binding_map(proof["scheduler_source_sha256"])
    return proof


def check_smoke_worker_metadata(a, plan, observed=None):
    """Inspect actual saved smoke terminals; no new process observation or task."""
    certificate = a.bound_json(plan["smoke_certificate_path"], plan["smoke_certificate_sha256"])
    exact(certificate, {"schema": "paper3-dynamic-real-model-bridge-smoke-v1", "status": "PASS",
        "actual_model_execution": True, "frozen_algorithm_modified": False,
        "model_worker_bitwise_invariance_claimed": False,
        "all_24_stage_f1_initial_deployment_and_causal_fields_verified": True}, "saved smoke certificate")
    reference = certificate["contract"]
    contract = a.bound_json(reference["path"], reference["sha256"])
    exact(contract, {"execution_mode": "BRIDGE_SMOKE", "manifest_digest": MANIFEST,
        "input_bundle_digest": F1}, "saved smoke contract")
    root = safe_relative(RESULTS, contract["run_relative"])
    require({p.name for p in (root / "workers").iterdir()} == {"DW0001", "DW0002"}, "smoke worker domain differs")
    expected_rows = {}
    for worker, count in (("DW0001", 1), ("DW0002", 0)):
        directory = root / "workers" / worker
        require(not (directory / "failure.json").exists(), "saved smoke worker failure exists")
        files = {}
        values = {}
        for name in ("contract.json", "launched.json", "ready.json", "finished.json", "actual_exit.json"):
            files[name] = a.sha(directory / name)
            values[name] = read(directory / name)
        wc, launch, ready, finish, exit_record = (values[n] for n in
            ("contract.json", "launched.json", "ready.json", "finished.json", "actual_exit.json"))
        require(wc == {**contract, "worker_id": worker, "worker_root": str(directory)}, "smoke worker contract differs")
        for value in (launch, ready, finish, exit_record):
            require(value["contract_sha256"] == files["contract.json"], "smoke terminal contract binding differs")
        exact(ready, {"schema": "paper3-dynamic-worker-ready-v1", "worker_id": worker,
            "execution_mode": "BRIDGE_SMOKE"}, "smoke ready")
        exact(finish, {"schema": "paper3-dynamic-worker-finished-v1", "worker_id": worker,
            "execution_mode": "BRIDGE_SMOKE", "original_trajectories_returned_after_full_checks": True,
            "new_manual_seed_introduced": False, "scientific_algorithm_modified": False,
            "model_output_worker_invariance_claimed": False, "statistics_executed": False}, "smoke finish")
        exact(exit_record, {"schema": "paper3-dynamic-owned-worker-exit-v1", "actual_exit_code": 0,
            "finished_validated": True, "producer": "OWNING_FROZEN_PROCESS_BACKEND", "automatic_retry": False,
            "pid": launch["pid"], "actual_model_pid": ready["pid"]}, "smoke actual exit")
        require(finish["pid"] == ready["pid"], "smoke model PID differs")
        summary = finish["summary"]
        exact(summary, {"assigned_tasks": count}, "smoke assigned task count")
        require(summary.get("completed_tasks", 0) + summary.get("skipped_valid_tasks", 0) == count,
            "smoke completed task count differs")
        expected_rows[worker] = {"worker_id": worker, "started_processes": 1, "trajectory_claims": count,
            "completed_or_valid_skipped": count, "popen_pid": launch["pid"], "model_pid": ready["pid"],
            "actual_exit_code": 0, "launched_utc": launch["utc"], "finished_utc": finish["finished_utc"],
            "exit_observed_utc": exit_record["observed_utc"], "contract_sha256": files["contract.json"],
            "finished_sha256": files["finished.json"], "actual_exit_sha256": files["actual_exit.json"]}
        if observed is not None:
            for name, digest in files.items():
                require(observed["evidence_sha256"].get(str(directory / name)) == digest,
                    "erratum smoke evidence omits/differs actual worker terminal")
    if observed is not None:
        exact(observed, {"schema": "paper3-observed-smoke-process-count-v1", "started_workers": 2,
            "trajectory_workers": 1, "trajectory_tasks": 1,
            "corrected_worker_count_display": "2 started / 1 trajectory worker",
            "smoke_contract_sha256": reference["sha256"]}, "observed smoke process count")
        rows = observed["workers"]
        require(len(rows) == 2 and {row["worker_id"] for row in rows} == set(expected_rows), "observed smoke workers differ")
        for row in rows:
            require(row == expected_rows[row["worker_id"]], "observed smoke terminal row differs")
        require(all(Path(filename).resolve().is_relative_to(root) for filename in observed["evidence_sha256"]),
            "smoke evidence outside original smoke attempt")
        a.binding_map(observed["evidence_sha256"])
    return {"started_workers": 2, "trajectory_workers": 1, "trajectory_tasks": 1,
            "both_saved_actual_exit_codes_zero": True, "DW0002_assigned_completed_zero": True}


def check_delivery(a, plan, stats, stats_receipt, plan_sha):
    for root in (RECORD, CONTROL, ERRATUM_RECORD):
        require(not (root / "stopped.json").exists() and not (root / "failure.json").exists(), "successful attempt has failure/stop: " + str(root))
    a.sha(RECORD / "start.json")
    start = read(RECORD / "start.json")
    exact(start, {"plan_sha256": plan_sha, "producer": "AUTHORIZED_LEGACY_METADATA_RECOVERY_V2", "models_restarted": False}, "V2 sequence start")
    a.sha(RECORD / "STATISTICS_PROCESS_EXIT.json")
    exact(read(RECORD / "STATISTICS_PROCESS_EXIT.json"), {"actual_exit_code": 0, "producer": "OWNING_POPEN_WAIT", "automatic_retry": False}, "statistics actual exit")
    a.sha(CONTROL / "SEQUENCE_PROCESS_EXIT.json")
    exact(read(CONTROL / "SEQUENCE_PROCESS_EXIT.json"), {"actual_exit_code": 0, "producer": "OWNING_POPEN_WAIT", "automatic_retry": False}, "sequence wrapper exit")
    native_path = CONTROL / "SEQUENCE_NATIVE_EXIT.json"
    a.sha(native_path)
    native = read(native_path)
    exact(native, {"schema": "paper3-erratum-sequence-native-exit-observation-v1", "producer": "PINNED_NATIVE_QUERY_HANDLE",
        "pid": start["pid"], "actual_exit_code": 0, "v1_plan_sha256": plan_sha,
        "identity_unchanged": True, "owning_popen_exit_claimed": False}, "sequence native exit")
    a.sha(CONTROL / "SEQUENCE_NATIVE_IDENTITY.json")
    identity = read(CONTROL / "SEQUENCE_NATIVE_IDENTITY.json")
    require(native["identity"] == identity["identity"] and identity.get("query_synchronize_handle_retained") is True,
            "retained native handle identity differs")
    a.sha(RECORD / "finish.json")
    finish = read(RECORD / "finish.json")
    exact(finish, {"status": "DYNAMIC_STATISTICS_DELIVERY_COMPLETED"}, "sequence finish")
    result = finish["result"]
    reviewed = REPO / plan["reviewed_handoff_relative"]
    final = REPO / plan["final_handoff_relative"]
    zipped = REPO / plan["zip_relative"]
    exact(result, {"reviewed_package": str(reviewed), "final_package": str(final), "zip_path": str(zipped),
                  "previous_root_handoff_sha256": F50}, "sequence output identity")
    dm, reviewed_inventory = a.package(reviewed, "DELIVERY_MANIFEST.json",
        ("DELIVERY_MANIFEST.json", "DELIVERY_MANIFEST.json.sha256"), "paper3-saved-results-delivery-v1")
    exact(dm, {"replication_manifest_digest": MANIFEST, "original_protected_files_unchanged": 2535,
        "real_models_or_generators_executed_by_delivery": False, "new_statistics_or_bootstrap_executed_by_delivery": False,
        "root_handoff_modified": False, "package_root": str(reviewed)}, "reviewed delivery")
    require((reviewed / "DELIVERY_MANIFEST.json.sha256").read_text(encoding="utf-8").strip() ==
            a.sha(reviewed / "DELIVERY_MANIFEST.json") + "  DELIVERY_MANIFEST.json", "delivery manifest sidecar differs")
    for filename, digest in dm["results_report_files_sha256"].items():
        a.bound(filename, digest)
    a.bound(RESULTS / "DELIVERY_MANIFEST.json", a.sha(reviewed / "DELIVERY_MANIFEST.json"))
    a.sha(RESULTS / "DELIVERY_MANIFEST.json.sha256")
    require((RESULTS / "DELIVERY_MANIFEST.json.sha256").read_text(encoding="utf-8").strip() ==
            a.sha(reviewed / "DELIVERY_MANIFEST.json") + "  DELIVERY_MANIFEST.json", "results delivery manifest sidecar differs")
    for name in (*REPORTS, DRAFT):
        a.bound(RESULTS / name, dm["package_files_sha256"][name])
    for name, digest in stats["outputs_sha256"].items():
        a.bound(reviewed / "statistics" / name, digest)
    pm, final_inventory = a.package(final, "FINAL_PACKAGE_MANIFEST.json", ("FINAL_PACKAGE_MANIFEST.json",), "paper3-dynamic-final-package-v1")
    old_draft_sha = dm["package_files_sha256"][DRAFT]
    exact(pm, {"manifest_digest": MANIFEST, "input_bundle_digest": F1, "dynamic_attempt_id": "A_DYNAMIC_0002",
        "previous_root_handoff_sha256": F50, "root_handoff_sha256": old_draft_sha, "static_success_fabricated": False}, "V1 final package")
    require(result["root_handoff_sha256"] == old_draft_sha, "first root draft linkage differs")
    for relative, digest in reviewed_inventory.items():
        a.bound(final / "reviewed_delivery" / relative, digest)
    a.zip(zipped, result["zip_sha256"], final_inventory)
    a.binding_map(read(final / "DYNAMIC_PROVENANCE_INDEX.json"))
    check_publication(a, final / "root_publication", F50, old_draft_sha)

    a.sha(ERRATUM_PLAN)
    ep = read(ERRATUM_PLAN)
    exact(ep, {"schema": "paper3-smoke-count-erratum-plan-v1", "manifest_digest": MANIFEST, "input_bundle_digest": F1,
        "v1_plan_sha256": plan_sha, "root_metadata_erratum_publication_authorized": True,
        "automatic_statistics_or_model_retry": False}, "erratum plan")
    require(Path(ep["v1_plan_path"]).resolve() == PLAN, "erratum V2 plan path differs")
    exact(ep, {"proof_path": str(ERRATUM_PROOF), "proof_sha256": ERRATUM_PROOF_SHA,
        "implementation_sha256": ERRATUM_PINS}, "erratum source certification")
    check_erratum_proof(a, plan)
    native_ref = ep["v1_native_exit_observation"]
    require(Path(native_ref["path"]).resolve() == native_path and native_ref["sha256"] == a.sha(native_path), "erratum native proof differs")
    a.sha(ERRATUM_RECORD / "finish.json")
    ef = read(ERRATUM_RECORD / "finish.json")
    exact(ef, {"status": "SMOKE_COUNT_METADATA_ERRATUM_COMPLETED", "statistics_bytes_unchanged": True,
               "previous_root_handoff_sha256": old_draft_sha}, "erratum finish")
    corrected = REPO / ep["target_relative"]
    corrected_zip = REPO / ep["zip_relative"]
    exact(ef, {"package": str(corrected), "zip": str(corrected_zip)}, "erratum output identity")
    em, corrected_inventory = a.package(corrected, "ERRATUM_MANIFEST.json",
        ("ERRATUM_MANIFEST.json", "ERRATUM_MANIFEST.json.sha256"), "paper3-superseding-metadata-erratum-package-v1")
    exact(em, {"manifest_digest": MANIFEST, "input_bundle_digest": F1, "supersedes_final_package": str(final),
        "supersedes_zip_sha256": result["zip_sha256"], "previous_root_handoff_sha256": old_draft_sha,
        "root_handoff_sha256": ef["root_handoff_sha256"], "earliest_archived_root_handoff_sha256": F50,
        "statistics_bytes_unchanged": True, "canonical_v1_results_reports_modified": False}, "erratum package")
    require((corrected / "ERRATUM_MANIFEST.json.sha256").read_text(encoding="utf-8").strip() ==
            a.sha(corrected / "ERRATUM_MANIFEST.json") + "  ERRATUM_MANIFEST.json", "erratum sidecar differs")
    a.zip(corrected_zip, ef["zip_sha256"], corrected_inventory)
    for relative, digest in final_inventory.items():
        a.bound(corrected / "original_v1_final_package" / relative, digest)
    a.bound(corrected / "original_v1_archive" / zipped.name, result["zip_sha256"])
    erratum_path = corrected / "ERRATUM.json"
    a.sha(erratum_path)
    erratum = read(erratum_path)
    exact(erratum, {"schema": "paper3-smoke-count-metadata-erratum-v1", "status": "CERTIFIED_METADATA_ONLY",
        "supersedes": str(final), "original_package_inventory": final_inventory, "original_zip_sha256": result["zip_sha256"],
        "started_smoke_workers": 2, "trajectory_smoke_workers": 1, "trajectory_tasks": 1,
        "all_statistics_bytes_preserved": True, "canonical_v1_reports_preserved": True,
        "v1_sources_plans_proofs_and_receipts_preserved": True, "models_or_statistics_executed_by_erratum": False,
        "statistics_manifest_sha256": a.sha(STATS / "statistics_manifest.json"),
        "statistics_receipt_sha256": a.sha(STATS / "statistics_execution_receipt.json")}, "metadata erratum")
    smoke_path = corrected / "SMOKE_PROCESS_COUNT_EVIDENCE.json"
    a.sha(smoke_path)
    smoke_evidence = check_smoke_worker_metadata(a, plan, read(smoke_path))
    require(erratum["statistics_files_sha256"] == {str(STATS / n): h for n, h in stats["outputs_sha256"].items()}, "erratum statistics inventory differs")
    require(set(erratum["changed_reports"]) == set(REPORTS) | {DRAFT}, "corrected report inventory differs")
    corrected_paths = [str(corrected / "corrected_reports" / n) for n in REPORTS]
    for name, change in erratum["changed_reports"].items():
        exact(change, {"source_sha256": dm["package_files_sha256"][name],
            "smoke_cells_changed": 1 if name in ("EXECUTION_SUMMARY.md", DRAFT) else 0,
            "appendix_added": True, "all_other_report_bytes_preserved": True,
            "corrected_report_entry_paths": corrected_paths}, "report erratum change")
        path = a.bound(corrected / "corrected_reports" / name, change["corrected_sha256"])
        content = path.read_text(encoding="utf-8")
        require("2 started / 1 trajectory worker" in content and all(n in content for n in corrected_paths), "corrected report entry index differs")
    corrected_draft_sha = erratum["changed_reports"][DRAFT]["corrected_sha256"]
    require(corrected_draft_sha == ef["root_handoff_sha256"], "corrected root draft SHA differs")
    check_publication(a, corrected / "root_publication", old_draft_sha, corrected_draft_sha)
    a.bound(REPO / ROOT_HANDOFF, corrected_draft_sha)
    a.sha(CONTROL / "ERRATUM_PROCESS_EXIT.json")
    exact(read(CONTROL / "ERRATUM_PROCESS_EXIT.json"), {"actual_exit_code": 0, "producer": "OWNING_POPEN_WAIT"}, "erratum process exit")
    a.sha(CONTROL / "finish.json")
    supervisor = read(CONTROL / "finish.json")
    exact(supervisor, {"status": "RECOVERY_SEQUENCE_AND_METADATA_ERRATUM_COMPLETED", "sequence_finish": finish,
                       "erratum_finish": ef}, "supervisor finish")
    a.checks["delivery"] = {"sequence_native_exit_zero_receipt_verified": True, "statistics_process_exit_zero": True,
        "erratum_process_exit_zero": True, "supervisor_legal_finish_verified": True,
        "reviewed_package_files": len(reviewed_inventory), "first_final_package_files": len(final_inventory),
        "erratum_package_files": len(corrected_inventory), "zip_member_hashes_verified": a.zipped_files_checked,
        "root_archive_chain": [F50, old_draft_sha, corrected_draft_sha], "corrected_reports": corrected_paths,
        "statistics_bytes_preserved": True, "current_handoff": str(REPO / ROOT_HANDOFF), "current_handoff_sha256": corrected_draft_sha}
    a.checks["delivery"]["actual_smoke_worker_metadata"] = smoke_evidence


def metadata_contract_preflight(args):
    """Cheap contract check only; intentionally cannot certify final integrity."""
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, "auditor requires -I -S -B")
    require(REPO == Path("D:/dt-talk/DT_LIFECYCLE_ESCALATION").resolve(), "auditor repository differs")
    require(args.expected_plan_sha256 == PLAN_SHA, "auditor only accepts the pinned finalized V2 plan")
    a = Auditor()
    plan = a.bound_json(PLAN, PLAN_SHA)
    exact(plan, {"schema": "paper3-dynamic-delivery-plan-v1", "manifest_digest": MANIFEST,
        "input_bundle_digest": F1, "record_root": str(RECORD)}, "metadata plan")
    manifest = read(RESULTS / "provenance_manifest.json")
    require(manifest["manifest_digest"] == MANIFEST and manifest["input_bundle_digest"] == F1,
        "metadata manifest identity differs")
    gate = read(RESULTS / "full_experiment_integrity_gate.json")
    exact(gate, {"manifest_digest": MANIFEST, "trajectories": 1200, "paired_groups": 240,
        "scientific_integrity_pass": True}, "metadata saved gate")
    required = {"schema", "task", "valid", "trajectory_rows", "manifest_digest", "input_bundle_digest",
        "performance_based_continuation", "full_24_stage_input_parity_checked", "future_online_access_violation_count",
        "statistics_executed", "initial_state_hash", "deployment_tier", "deployment_filter_hash", "bank_hash",
        "stage_input_hashes", "output_hash", "audit_relative", "audit_hash", "rng_relative", "rng_file_sha256",
        "attempt_csv_relative", "attempt_csv_hash", "runtime_receipt_path", "runtime_receipt_sha256"}
    expected_tasks = {(c, seed, scenario, method, config) for c in range(33000, 33020)
        for seed in (7311, 7312, 7313) for scenario in SCENARIOS for method, config in METHODS.items()}
    found = set()
    alias_count = 0
    key_variants = set()
    files = sorted((RESULTS / "raw").glob("*.integrity.json"))
    require(len(files) == 1200, "metadata receipt count differs")
    for path in files:
        receipt = read(a.path(path))
        require(required <= receipt.keys(), "missing raw receipt fields: " + str(path) + " " + str(sorted(required - receipt.keys())))
        exact(receipt, {"schema": "paper3-batch20-replication-trajectory-receipt-v1", "valid": True,
            "trajectory_rows": 24, "manifest_digest": MANIFEST, "input_bundle_digest": F1,
            "performance_based_continuation": False, "full_24_stage_input_parity_checked": True,
            "future_online_access_violation_count": 0, "statistics_executed": False}, "metadata raw receipt")
        task = receipt["task"]
        require(set(task) == {"center_id", "seed", "scenario", "method", "config_id"}, "metadata task fields differ")
        identity = tuple(task[k] for k in ("center_id", "seed", "scenario", "method", "config_id"))
        require(identity in expected_tasks and identity not in found, "metadata task domain/duplicate differs")
        require(path.name == stem(task) + ".integrity.json", "metadata receipt stem differs")
        found.add(identity)
        if "audit_sha256" in receipt:
            require(receipt["audit_sha256"] == receipt["audit_hash"], "metadata receipt audit alias differs")
            alias_count += 1
        for key in ("output_hash", "audit_hash", "rng_file_sha256", "attempt_csv_hash", "runtime_receipt_sha256"):
            require(digest_string(receipt[key]), "metadata receipt digest field differs: " + key)
        for key in ("audit_relative", "rng_relative", "attempt_csv_relative", "runtime_receipt_path"):
            a.path(safe_relative(RESULTS, receipt[key]))
        hashes = receipt["stage_input_hashes"]
        require(len(hashes) == 24 and [item["stage"] for item in hashes] == list(range(1, 25)), "metadata stage domain differs")
        for item in hashes:
            require({"stage", "D_upd_hash", "D_assess_hash", "D_srv_hash"} <= item.keys(), "metadata stage hash keys differ")
            require(all(digest_string(item[k]) for k in ("D_upd_hash", "D_assess_hash", "D_srv_hash")), "metadata stage digest differs")
        key_variants.add(tuple(sorted(receipt)))
    require(found == expected_tasks, "metadata receipt task coverage differs")
    for group in gate["groups"].values():
        require({"receipt_sha256", "initial_state_hash", "scenario_hash", "deployment_tier",
            "deployment_filter_hash", "bank_hash", "five_methods", "all_24_stage_input_fields_equal"} <= group.keys(),
            "metadata gate group keys differ")
        require(set(group["receipt_sha256"]) == set(METHODS), "metadata gate method keys differ")
    sample = RESULTS / "raw/B0_Frozen_ratio10_33000_7311_C0.csv"
    with a.path(sample).open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        require(set(INPUT_FIELDS) | {"stage", "config_id", "method", "center_id", "seed", "scenario"} <= set(reader.fieldnames or ()),
            "fixed raw CSV sample contract differs")
        rows = list(reader)
        require(len(rows) == 24 and [row["stage"] for row in rows] == [str(n) for n in range(1, 25)], "fixed raw CSV sample stages differ")
    check_erratum_proof(a, plan)
    smoke = check_smoke_worker_metadata(a, plan)
    planned = {}
    for key in ("reviewed_handoff_relative", "final_handoff_relative", "zip_relative"):
        path = safe_relative(REPO, plan[key])
        require(path.is_relative_to(REPO / "handoffs"), "planned package outside handoffs")
        planned[key] = {"path": str(path), "exists_now": path.exists()}
    require(len({item["path"] for item in planned.values()}) == 3, "planned package paths alias")
    a.stable()
    return {"schema": "paper3-independent-metadata-contract-preflight-v1", "status": "PASS",
        "observed_utc": utc(), "auditor_sha256": a.sha(Path(__file__)), "repository": str(REPO),
        "mode": "METADATA_CONTRACT_PREFLIGHT_ONLY", "scientific_acceptance": "NOT_PERFORMED",
        "receipt_json_contracts_checked": len(files), "receipt_key_variants": len(key_variants),
        "audit_aliases_present_and_equal": alias_count, "fixed_raw_csv_sample": str(sample),
        "fixed_raw_sample_rows": len(rows), "saved_smoke_worker_metadata": smoke,
        "erratum_proof004_sha256": ERRATUM_PROOF_SHA, "erratum_own4_exact_sha_verified": True,
        "planned_outputs": planned, "missing_future_packages_not_treated_as_completion": True,
        "files_hashed_small_source_and_metadata_only": len(a.expected), "file_bytes_hashed": a.bytes_hashed,
        "all_CSV_or_environment_bytes_hashed": False, "no_files_written": True,
        "no_models_generators_or_statistics_executed": True, "no_endpoints_bootstrap_or_CI_computed": True}


def run(args):
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode, "auditor requires -I -S -B")
    require(REPO == Path("D:/dt-talk/DT_LIFECYCLE_ESCALATION").resolve(), "auditor repository differs")
    require(args.expected_plan_sha256 == PLAN_SHA, "auditor only accepts the pinned finalized V2 plan")
    a = Auditor()
    plan = a.bound_json(PLAN, args.expected_plan_sha256)
    require(Path(plan["record_root"]).resolve() == RECORD, "V2 record path differs")
    manifest = a.bound_json(RESULTS / "provenance_manifest.json", MANIFEST_FILE_SHA)
    require(canonical({k: v for k, v in manifest.items() if k != "manifest_digest"}) == MANIFEST, "manifest canonical binding differs")
    exact(manifest, {"manifest_digest": MANIFEST, "input_bundle_digest": F1,
        "historical_environment_reproduced": False, "original_records_mixed_into_new_results": False}, "replication manifest")
    require(Path(manifest["paths"]["repo"]).resolve() == REPO and Path(manifest["paths"]["results_root"]).resolve() == RESULTS, "manifest target paths differ")
    allowed_external = set(manifest["environment"]["bound_files_sha256"])
    allowed_external.update(manifest.get("stage_b_dependencies_sha256", {}))
    descriptor = manifest["environment"]["model_runtime_descriptor"]
    allowed_external.update(descriptor.get("installation_evidence_files_sha256", {}))
    a.external_allowed = {str(Path(n).resolve()).casefold() for n in allowed_external}
    for key in ("critical_files_sha256", "original_python_dependency_sha256", "original_protected_snapshot"):
        for relative, digest in manifest[key].items():
            a.bound(safe_relative(REPO, relative), digest)
    require(len(manifest["original_protected_snapshot"]) == 2535, "original protection inventory differs")
    for relative, digest in manifest["executor_sha256"].items():
        a.bound(safe_relative(Path(manifest["paths"]["executor_root"]), relative), digest)
    executor_root = Path(manifest["paths"]["executor_root"])
    executor_inventory = {path.relative_to(executor_root).as_posix(): a.sha(path)
        for path in sorted(executor_root.rglob("*.py")) if "__pycache__" not in path.parts}
    require(executor_inventory == manifest["executor_sha256"], "executor source inventory changed or gained files")
    original_python = {path.relative_to(REPO).as_posix(): a.sha(path)
        for folder in ("core", "imported", "scripts") for path in sorted((REPO / folder).rglob("*.py"))
        if "__pycache__" not in path.parts}
    require(original_python == manifest["original_python_dependency_sha256"], "original source closure changed or gained files")
    for relative, digest in manifest["input_files_sha256"].items():
        a.bound(safe_relative(Path(manifest["paths"]["input_run"]), relative), digest)
    a.binding_map(manifest["environment"]["bound_files_sha256"])
    a.binding_map(manifest["stage_b_dependencies_sha256"])
    a.binding_map(plan["activation_evidence_sha256"])
    a.checks["frozen_bytes"] = {"critical_files": len(manifest["critical_files_sha256"]),
        "original_python_files": len(original_python), "executor_files": len(executor_inventory),
        "protected_original_files": len(manifest["original_protected_snapshot"]),
        "environment_files": len(manifest["environment"]["bound_files_sha256"]),
        "F1_files": len(manifest["input_files_sha256"]), "source_inventories_exact": True,
        "runtime_environment_predicate_executed_by_this_auditor": False}
    gate = a.bound_json(RESULTS / "full_experiment_integrity_gate.json", GATE_SHA)
    exact(gate, {"scientific_integrity_pass": True, "manifest_digest": MANIFEST, "trajectories": 1200,
        "paired_groups": 240, "old_results_reused": False, "all_inputs_F1": True, "future_flags_false": True,
        "outcomes_used_to_select_protocol": False, "not_unseen_heldout": True}, "full gate")
    cert = a.bound_json(CERT, CERT_SHA)
    a.bound(RECORD / CERT.name, CERT_SHA)
    exact(cert, {"schema": "paper3-dynamic-full-integrity-certificate-v1", "status": "PASS", "manifest_digest": MANIFEST,
        "input_bundle_digest": F1, "trajectories": 1200, "paired_groups": 240, "static_phase_success_fabricated": False}, "full certificate")
    exact(cert["scientific_integrity"], {"manifest_digest": MANIFEST, "critical_scientific_bytes_unchanged": True,
        "environment_file_bytes_checked": True, "original_full_snapshot_checked": True,
        "all_F1_inputs_checked": True, "historical_environment_reproduced": False}, "full closure certificate")
    a.binding_map(cert["evidence_sha256"])
    initial = a.bound_json(RESULTS / "initial_state_manifest.json", INITIAL_SHA)
    exact(initial, {"manifest_digest": MANIFEST, "input_bundle_digest": F1, "expected_cases": 60, "completed_cases": 60}, "initial manifest")
    require({(item["center_id"], item["seed"]) for item in initial["states"]} ==
        {(c, seed) for c in range(33000, 33020) for seed in (7311, 7312, 7313)}, "sixty initial case domain differs")
    for item in initial["states"]:
        a.bound(safe_relative(RESULTS, item["path"]), item["sha256"])
        a.bound(safe_relative(RESULTS, item["receipt_path"]), item["receipt_sha256"])
    check_raw(a, gate, manifest)
    stats, receipt = check_statistics(a, manifest)
    for filename, digest in cert["evidence_sha256"].items():
        require(stats["input_bindings_sha256"].get(filename) == digest, "certificate reference not bound by statistics")
    require(stats["input_bindings_sha256"].get(str(PLAN)) == args.expected_plan_sha256, "final plan is not statistics bound")
    check_delivery(a, plan, stats, receipt, args.expected_plan_sha256)
    supervisor_exit = "NOT_VERIFIED"
    supervisor_observation_sha = None
    if args.supervisor_exit_observation and Path(args.supervisor_exit_observation).is_file():
        observation_path = Path(args.supervisor_exit_observation).resolve()
        require(observation_path == HERE / "ROOT_SUPERVISOR_NATIVE_EXIT_002.json", "unexpected root supervisor observation")
        supervisor_observation_sha = args.supervisor_exit_sha256 or a.sha(observation_path)
        observation = a.bound_json(observation_path, supervisor_observation_sha)
        a.sha(CONTROL / "start.json")
        supervisor_start = read(CONTROL / "start.json")
        exact(supervisor_start, {"plan_sha256": args.expected_plan_sha256, "automatic_retry": False}, "supervisor start")
        exact(observation, {"schema": "paper3-root-supervisor-native-exit-v1", "actual_exit_code": 0,
            "pid": supervisor_start["pid"], "identity_unchanged": True,
            "owning_popen_exit_claimed": False}, "external supervisor exit")
        require(observation.get("producer") == "PINNED_NATIVE_QUERY_HANDLE", "supervisor exit must be a retained native handle observation")
        require(observation.get("plan_sha256", observation.get("v1_plan_sha256")) == args.expected_plan_sha256, "supervisor exit plan differs")
        identity_path = HERE / "ROOT_SUPERVISOR_NATIVE_IDENTITY_002.json"
        identity = a.bound_json(identity_path, SUPERVISOR_IDENTITY_SHA)
        exact(identity, {"schema": "paper3-root-supervisor-native-identity-v1", "pid": supervisor_start["pid"],
            "plan_sha256": args.expected_plan_sha256, "query_synchronize_handle_retained": True}, "supervisor held identity")
        require(identity["identity"] == observation["identity"], "supervisor native identity changed")
        native_identity = observation["identity"]
        require(native_identity.get("pid") == supervisor_start["pid"] and
                type(native_identity.get("creation_filetime")) is int and native_identity["creation_filetime"] > 0,
                "supervisor exact kernel FILETIME identity missing")
        launch_path = HERE / "durable_launch002/launch_spec.json"
        creation_path = HERE / "durable_launch002/creation.json"
        require(observation["launch_spec_sha256"] == SUPERVISOR_LAUNCH_SHA and
                observation["creation_receipt_sha256"] == SUPERVISOR_CREATION_SHA, "root-owned supervisor creation bytes differ")
        launch = a.bound_json(launch_path, observation["launch_spec_sha256"])
        creation = a.bound_json(creation_path, observation["creation_receipt_sha256"])
        require(identity["launch_spec_sha256"] == observation["launch_spec_sha256"] and
                identity["creation_receipt_sha256"] == observation["creation_receipt_sha256"], "supervisor launch identity binding differs")
        exact(creation, {"return_value": 0, "pid": supervisor_start["pid"]}, "durable supervisor creation")
        exact(launch, {"plan_sha256": args.expected_plan_sha256}, "durable supervisor launch")
        require(observation["identity"]["command_line"] == launch["command_line"] and
            Path(observation["identity"]["image"]).resolve() == Path(launch["interpreter"]).resolve(),
            "supervisor native image/full command differs from durable creation")
        supervisor_exit = "VERIFIED_FROM_ROOT_OWNED_NATIVE_EXIT_OBSERVATION"
    elif args.supervisor_exit_sha256:
        raise AcceptanceError("specified supervisor native exit observation is missing")
    a.stable()
    return {"schema": "paper3-independent-final-readonly-acceptance-v1", "status": "PASS" if supervisor_exit != "NOT_VERIFIED" else "PARTIAL",
        "observed_utc": utc(), "repository": str(REPO), "results": str(RESULTS), "auditor_sha256": a.sha(Path(__file__)),
        "manifest_digest": MANIFEST, "input_bundle_digest": F1, "expected_plan_sha256": args.expected_plan_sha256,
        "full_gate_sha256": GATE_SHA, "full_certificate_sha256": CERT_SHA, "checks": a.checks,
        "supervisor_os_exit": supervisor_exit, "supervisor_exit_observation_sha256": supervisor_observation_sha,
        "unique_files_hashed": len(a.expected), "file_bytes_hashed": a.bytes_hashed,
        "original_protected_files_verified": 2535, "environment_bound_files_verified": len(manifest["environment"]["bound_files_sha256"]),
        "F1_bound_files_verified": len(manifest["input_files_sha256"]), "no_models_generators_or_statistics_executed": True,
        "no_files_written": True, "no_new_endpoints_bootstrap_or_CI_computed": True,
        "historical_environment_reproduced": False, "new_unseen_heldout_claimed": False,
        "manuscript_automatically_frozen": False,
        "observation_scope": "Saved bytes, schemas, pairing fields, table dimensions, exact ZIP members and publication chain; final file metadata checked stable. Recorded native exits are validated, not recreated."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-plan-sha256", default=PLAN_SHA)
    parser.add_argument("--supervisor-exit-observation", default=str(HERE / "ROOT_SUPERVISOR_NATIVE_EXIT_002.json"))
    parser.add_argument("--supervisor-exit-sha256")
    parser.add_argument("--metadata-contract-preflight", action="store_true",
        help="Read receipt JSON contracts and one raw CSV sample; never run full acceptance or hash all data/environment")
    args = parser.parse_args()
    try:
        result = metadata_contract_preflight(args) if args.metadata_contract_preflight else run(args)
    except Exception as error:
        print(json.dumps({"schema": "paper3-independent-final-readonly-acceptance-v1", "status": "BLOCKED",
            "observed_utc": utc(), "error_type": type(error).__name__, "message": str(error),
            "no_files_written": True, "no_models_generators_or_statistics_executed": True}, sort_keys=True), flush=True)
        return 1
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
