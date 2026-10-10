"""Read-only V4 acceptance: science, published artifacts and new finalization.

This file is deliberately outside pipeline.OWN and the production import graph.
It imports only the standard library, never starts a process, never writes a file,
never imports a project module, and never computes/recomputes a model endpoint,
bootstrap, confidence interval, or model output.  Root may save stdout separately
to a NEW exclusive observation file.  Run only after the producer has finished.

Usage:
  <metadata-python> -I -S -B final_readonly_acceptance.py \
    --expected-plan-sha256 <actual finalized V2 plan SHA> \
    --recovery-plan-sha256 <actual independent metadata-recovery plan SHA> \
    --finalization-plan-sha256 <actual postpublication finalization plan SHA> \
    --finalization-exit-observation <root-owned finalization exit JSON> \
    --finalization-exit-sha256 <its actual SHA>

The original metadata producer's historical OS exit remains unobserved. A new
read-only finalization process validates its completed published artifacts and
supplies an independent owning/native zero exit. PASS is explicitly scoped to
scientific artifacts and that new finalization, never all historical OS exits.
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
import subprocess
import sys
import zipfile


HERE = Path(__file__).resolve().parent
BASE = HERE.parent
REPO = BASE.parents[1]
RESULTS = REPO / "results/p7_7_integrity_replication_batch20_env_v3"
STATS = RESULTS / "statistics_batch20_env_v3"
V2 = BASE / "replication_dynamic_delivery_recovery_v2"
V3 = BASE / "replication_dynamic_delivery_recovery_v3"
FROZEN_V3_AUDITOR = V3 / "final_readonly_acceptance.py"
FROZEN_V3_AUDITOR_SHA = "b0c0a2cc07a438067e8eb450ff748ca7467df2d8ffe1c299367e6acaec9ad734"
ORIGINAL_AUDITOR = V2 / "final_readonly_acceptance.py"
ORIGINAL_AUDITOR_SHA = "660c19ac4830672b9cf53b94d8b56aa6b7c214007307ea532d7ab8823d85d8b1"
PLAN = V2 / "RECOVERY_DELIVERY_PLAN_002.json"
PLAN_SHA = "174c04348357f05537a034db69d9f2c5941b4f5ef700783ee02087f0cb5deba5"
SUPERVISOR_IDENTITY_SHA = "1b24658842175caaba27a64cb6fc4178e0875da5b4bc1a99901ae0378fa0ea18"
SUPERVISOR_LAUNCH_SHA = "bf9551297e1ba857f2d48cb720567042cce726ad1628d5acbac54f97f5b28971"
SUPERVISOR_CREATION_SHA = "c70eb875f81c0f2e694f705845650dbcf5507c2f04d61daeadde729d3c62112c"
RECORD = V2 / "sequence002"
CONTROL = V2 / "supervisor002"
ERRATUM_ROOT = BASE / "replication_dynamic_delivery_erratum_v1"
METADATA_RECOVERY = BASE / "replication_dynamic_delivery_erratum_recovery_v2"
METADATA_HELPER = METADATA_RECOVERY / "metadata_recovery.py"
ERRATUM_PLAN = METADATA_RECOVERY / "ERRATUM_RECOVERY_PLAN_005.json"
ERRATUM_RECORD = METADATA_RECOVERY / "erratum_recovery004"
ROOT_RECOVERY_START = METADATA_RECOVERY / "ROOT_ERRATUM_RECOVERY_PROCESS_START_004.json"
ROOT_RECOVERY_EXIT = METADATA_RECOVERY / "ROOT_ERRATUM_RECOVERY_PROCESS_EXIT_004.json"
OLD_ROOT_OBSERVER_FAILURE = METADATA_RECOVERY / "ROOT_EXIT_OBSERVER_FAILURE_004.json"
OLD_ROOT_OBSERVER_FAILURE_SHA = "92de2eec50b9be2200eb02296b64e45ff927452d6eb4911ec577e24ebfa4f5c7"
OLD_METADATA_START_SHA = "29e4c8004066be28dc76d8697f379ce82789b8f7ae8bd26cf9c18381ecb59421"
OLD_METADATA_FINISH_SHA = "1bc8dba3a9f06c998ab786d0a9ab5300dba93338fb8e86de6c478db970268e03"
OLD_METADATA_PLAN_SHA = "44cb35e0df7b584e45944956e64c12d9706eb1aa7acceb28b2302a4e97f15dff"
POST_FINALIZATION = BASE / "replication_metadata_postpublication_finalize_v1"
POST_PLAN = POST_FINALIZATION / "POSTPUBLICATION_FINALIZATION_PLAN_001.json"
POST_RECORD = POST_FINALIZATION / "finalize001"
POST_START = POST_FINALIZATION / "POSTPUBLICATION_PROCESS_START_001.json"
POST_EXIT = POST_FINALIZATION / "POSTPUBLICATION_PROCESS_EXIT_001.json"
POST_OWN = ("postpublication_finalize.py", "root_finalize_launch.py", "test_postpublication_finalize.py")
POST_NATIVE = POST_FINALIZATION / "POSTPUBLICATION_NATIVE_EXIT_OBSERVATION_001.json"
POST_PROOF = POST_FINALIZATION / "POSTPUBLICATION_FINALIZATION_TEST_RESULTS_001.json"
POST_PLAN_SHA = "07d20299854c910ba26cfae1977c80b04ff40cde0c0662b3596897bd558729ef"
POST_PROOF_SHA = "d17c3fc7a96fe4572f9442387b7752cc47756ef0dba5f04339fcb4b6fc11461d"
POST_SCOPE = "ARTIFACT_FINALIZATION_AFTER_EXIT_OBSERVER_FAILURE"
POST_SOURCE_PINS = {str(POST_FINALIZATION / name): digest for name, digest in {
    "postpublication_finalize.py": "ea6d1665d621769341864456abf8f16674e9c019e02f9f4298e5969b56ecb0cf",
    "root_finalize_launch.py": "d6c9d553f49cd6c41695112a1632b8ec7dda706d72568565838ab968bb5734ca",
    "test_postpublication_finalize.py": "19cbf8374284bf12f0a9aef8dd7547086e07bb6b3e6f1d56a31e06b55f1d6a0e"}.items()}
PUBLISHED_H2 = "2a522ae64713ffc6e3cbe1389a7faac15d267dd123675590f5f813d50cf33368"
PUBLISHED_ERRATUM_ZIP_SHA = "b6e5ba6660b1c256be7775823b75074342a9b8cf0a1f1336ec0cde735fbf7df8"
PUBLISHED_ERRATUM_ZIP_BYTES = 16949617
PUBLISHED_ERRATUM_MANIFEST_SHA = "2ada566465c1fe4f2bf4b6db0da22d8404cd6a0bdf8c7870820bb27e4df88bd8"
PUBLISHED_STATISTICS_MANIFEST_SHA = "a2cd080532db281ca60ae89ee9edf5e272552689f8be9220eaf7c7857b3f1468"
PUBLISHED_STATISTICS_RECEIPT_SHA = "82585cf06c15e2bebc2d37bea90ccb9b6f24aa78745c00f6fd3378a0a0742dec"
POST_PACKAGE = REPO / "handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001"
POST_BOUND_FILES = {
    str(METADATA_RECOVERY / "ERRATUM_RECOVERY_PLAN_005.json"): OLD_METADATA_PLAN_SHA,
    str(METADATA_RECOVERY / "BOUNDARY_STOP_RECOVERY_TEST_RESULTS_005.json"): "5e488c9dea6a775a4f5bbafab359a942a0f6d61825f873c47d664f468aa9b1af",
    str(ROOT_RECOVERY_START): OLD_METADATA_START_SHA,
    str(ERRATUM_RECORD / "finish.json"): OLD_METADATA_FINISH_SHA,
    str(OLD_ROOT_OBSERVER_FAILURE): OLD_ROOT_OBSERVER_FAILURE_SHA,
    str(ERRATUM_ROOT / "metadata_erratum.py"): "3461322dd57af084d46a98d6cdb66abca473d006902fb90e37694013d92bebce",
    str(ERRATUM_ROOT / "erratum_watch.py"): "cdf0d78d2930b6d7c2211b0336378ce226bb6ea39a39be0d6377cd343c8fbcd2",
    str(POST_PACKAGE / "ERRATUM_MANIFEST.json"): PUBLISHED_ERRATUM_MANIFEST_SHA,
    str(POST_PACKAGE.with_suffix(".zip")): PUBLISHED_ERRATUM_ZIP_SHA,
    str(REPO / "PAPER3_FINAL_REPLICATION_HANDOFF.md"): PUBLISHED_H2,
    str(STATS / "statistics_manifest.json"): PUBLISHED_STATISTICS_MANIFEST_SHA,
    str(STATS / "statistics_execution_receipt.json"): PUBLISHED_STATISTICS_RECEIPT_SHA}
OLD_FAILURES = {str(CONTROL / "stopped.json"): "3d71c8823b88c50d5e633e4572ba0d780b1ece779a13b8e796d36bdca758563d",
    str(CONTROL / "ERRATUM_PROCESS_EXIT.json"): "ff0b511468e4f1c606f7e273f941f7e3f1f6f82f2a44b74ab28915381b21138e",
    str(V2 / "ROOT_SUPERVISOR_NATIVE_EXIT_002.json"): "db00563f0cd9c8f332b088431b2e41cc6949a5b2c4480a3b7fcdb845f1487f33",
    str(ERRATUM_ROOT / "erratum_recovery002/stopped.json"): "1625d90fa972c31e8abcf77ee952446f9e5649ad42dc5af70047257677f8c89d",
    str(CONTROL / "erratum_process.log"): "95a820574312dab257324d7e2ef3516ec95a8d8dda2a62b068b607af68c88986",
    str(ERRATUM_ROOT / "erratum_recovery002/start.json"): "b7d26f5d8ec6b03a7d02ce57397fa9b4794160e22292f311003b5db353103d6f"}
OLD_ERRATUM_PLAN = ERRATUM_ROOT / "ERRATUM_RECOVERY_PLAN_002.json"
OLD_ERRATUM_PLAN_SHA = "04f22e5a01ea11199ed8847593d796142ecf5dfbcd1b06d2ca7e0fa9445a440c"
METADATA_OWN = ("metadata_recovery.py", "test_metadata_recovery.py", "root_erratum_launch003.py")
RECOVERY_PROOF = METADATA_RECOVERY / "BOUNDARY_STOP_RECOVERY_TEST_RESULTS_005.json"
METADATA_PYTHON = Path("C:/Users/92487/anaconda3/envs/rcf-dti-py311/python.exe")
METADATA_PYTHON_SHA = "0562f573871cb16a2fb8de16e3d486e3dfd74bb83c7e87db265561917d05ad1a"
H1 = "c7b539bef23e3f43e1d663bc9240ab80cd325d2f1f7dd501e0b22cd18e3b8a3d"
SMOKE_PINS = {
    "journal/000004.json": "5cc9bced5a307086b992608a22abd0fd978838a1a17ee5c0feb4e87cc896e00b",
    "journal/000005.json": "5c7da86fd04a3b331b362e96491b56159c4ca24b4d96446736be3fdd2d03e77d",
    "workers/DW0001/commands/000002.json": "e982fc0b94769e2edcdd14ef8ffff02b154e52de857c84bb6fe7e95cbbf9d1f2",
    "workers/DW0002/commands/000001.json": "0b7d2b3db4b5d4353b0f72c8935d59748d298676a1bb83a49c834d68ddc493cc",
    "workers/DW0001/finished.json": "7c6648b219b939f7261d43798e73851fa5952ddb3e8c8c5037f9bc9ed44b208f",
    "workers/DW0002/finished.json": "34efcc10f600bb4ea86375e67a39c57267dab10738665635ff5300b8077387c3",
    "workers/DW0001/actual_exit.json": "bac5eecd8adfa2431603d0337c6a88641e71e34339d64e5876be245812bef98e",
    "workers/DW0002/actual_exit.json": "818f15fbb95139ad565a102cebd2983fa2cae9a187f1fe6bd6eac001b2c2851b"}
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


def check_scientific_auditor_preservation(a):
    """Compare verified source text; import neither auditor nor producer."""
    original_path = a.bound(ORIGINAL_AUDITOR, ORIGINAL_AUDITOR_SHA)
    original_payload = original_path.read_bytes()
    require(hashlib.sha256(original_payload).hexdigest() == ORIGINAL_AUDITOR_SHA, "original auditor AST bytes changed")
    current_path = Path(__file__)
    current_sha = a.sha(current_path)
    current_payload = current_path.read_bytes()
    require(hashlib.sha256(current_payload).hexdigest() == current_sha, "current auditor AST bytes changed")
    original, current = original_payload.decode("utf-8"), current_payload.decode("utf-8")
    def segments(text):
        return {node.name: ast.get_source_segment(text, node) for node in ast.parse(text).body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    old, new = segments(original), segments(current)
    unchanged = ("Auditor", "read", "exact", "safe_relative", "canonical", "stem",
        "check_raw", "check_statistics", "check_publication", "check_erratum_proof",
        "check_smoke_worker_metadata", "metadata_contract_preflight")
    require(all(old[name] == new[name] for name in unchanged), "original scientific/package audit functions changed")
    anchor = "    check_delivery("
    require(old["run"].split(anchor)[0] == new["run"].split(anchor)[0],
        "original full source/input/environment/scientific acceptance prefix changed")
    def region(text, start, end):
        require(text.count(start) == 1 and text.count(end) == 1, "package audit source region ambiguous")
        return text.split(start, 1)[1].split(end, 1)[0]
    first_start, first_end = '    dm, reviewed_inventory =', '    a.sha(ERRATUM_PLAN)'
    strengthened = new["check_delivery"].replace('    require(old_draft_sha == H1, "previous legally published root handoff SHA differs")\n', '')
    require(region(old["check_delivery"], first_start, first_end) == region(strengthened, first_start, first_end),
        "original reviewed/final package, ZIP or first root publication checks changed")
    corrected_start = '    a.sha(ERRATUM_RECORD / "finish.json")'
    corrected_end_old = '    a.sha(CONTROL / "ERRATUM_PROCESS_EXIT.json")'
    corrected_end_new = '    failures = check_old_failure_chain(a)'
    strengthened = strengthened.replace('    check_recovery_package_sources(a, corrected, ep, recovery_plan_sha, erratum)\n', '')
    strengthened = strengthened.replace('    boundary_evidence = check_smoke_boundary_recovery(a, plan, read(smoke_path))\n', '')
    require(region(old["check_delivery"], corrected_start, corrected_end_old) ==
        region(strengthened, corrected_start, corrected_end_new),
        "original corrected package, statistics preservation, ZIP or root publication checks changed")
    return {"original_auditor_sha256": ORIGINAL_AUDITOR_SHA,
        "unchanged_functions": list(unchanged), "full_scientific_prefix_byte_identical": True,
        "original_package_ZIP_and_root_checks_byte_identical": True,
        "additional_known_H1_and_metadata_recovery_checks": True}


def boundary_transform_from_frozen_source(a):
    source = a.bound(ERRATUM_ROOT / "metadata_erratum.py", ERRATUM_PINS[str(ERRATUM_ROOT / "metadata_erratum.py")])
    payload = source.read_bytes()
    require(hashlib.sha256(payload).hexdigest() == ERRATUM_PINS[str(source)], "original smoke AST bytes changed")
    text = payload.decode("utf-8")
    nodes = [n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == "inspect_smoke"]
    require(len(nodes) == 1, "original inspect_smoke is ambiguous")
    node = nodes[0]
    original = "\n".join(text.splitlines()[node.lineno - 1:node.end_lineno])
    old = "len(stop_commands)==(0 if n else 1)"
    new = "len(stop_commands) in ((0,1) if n else (1,))"
    require(original.count(old) == 1 and new not in original, "original narrow STOP predicate differs")
    adapted = original.replace(old, new)
    return {"function": "inspect_smoke", "original_source_sha256": ERRATUM_PINS[str(source)],
        "old_predicate": old, "new_predicate": new, "all_other_function_source_identical": True,
        "original_function_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "adapted_function_sha256": hashlib.sha256(adapted.encode()).hexdigest()}


def check_old_failure_chain(a):
    a.binding_map(OLD_FAILURES)
    exact(read(CONTROL / "stopped.json"), {"status": "STOPPED_FOR_DIAGNOSIS", "automatic_retry": False,
        "error": "RouteError", "message": "metadata erratum failed; no retry"}, "preserved supervisor failure")
    exact(read(ERRATUM_ROOT / "erratum_recovery002/stopped.json"), {"status": "STOPPED_FOR_DIAGNOSIS",
        "automatic_retry": False, "error": "ErratumError", "message": "smoke trajectory/idle worker coverage differs"},
        "preserved erratum failure")
    exact(read(CONTROL / "ERRATUM_PROCESS_EXIT.json"), {"actual_exit_code": 1, "pid": 26472,
        "producer": "OWNING_POPEN_WAIT"}, "preserved failed erratum owning exit")
    exact(read(ERRATUM_ROOT / "erratum_recovery002/start.json"), {"schema": "paper3-smoke-count-erratum-start-v1",
        "pid": 26472, "plan_sha256": OLD_ERRATUM_PLAN_SHA, "models_statistics_executed": False}, "old erratum start")
    native = read(V2 / "ROOT_SUPERVISOR_NATIVE_EXIT_002.json")
    exact(native, {"schema": "paper3-root-supervisor-native-exit-v1", "actual_exit_code": 1, "pid": 31860,
        "producer": "PINNED_NATIVE_QUERY_HANDLE", "identity_unchanged": True,
        "owning_popen_exit_claimed": False, "plan_sha256": PLAN_SHA}, "preserved supervisor native exit")
    exact(native["identity"], {"pid": 31860, "creation_filetime": 134360945847022492}, "preserved native identity")
    for path in (CONTROL / "finish.json", ERRATUM_ROOT / "erratum_recovery002/finish.json"):
        require(not path.exists(), "failed old attempt has a fabricated successful finish")
    return {"old_supervisor_actual_exit_code": 1, "old_erratum_actual_exit_code": 1,
        "old_failures_preserved": len(OLD_FAILURES), "old_failed_attempt_success_fabricated": False}


def check_recovery_plan(a, ep, expected_sha):
    require(digest_string(expected_sha), "explicit finalized recovery plan SHA required")
    a.bound(ERRATUM_PLAN, expected_sha)
    original = a.bound_json(OLD_ERRATUM_PLAN, OLD_ERRATUM_PLAN_SHA)
    recovery = ep.get("metadata_recovery")
    require(isinstance(recovery, dict), "metadata recovery certification absent")
    require(ep == {**original, "record_root": str(ERRATUM_RECORD), "metadata_recovery": recovery},
        "non-recovery original erratum plan fields changed")
    sources = recovery.get("source_sha256")
    require(isinstance(sources, dict) and set(sources) == {str(METADATA_RECOVERY / n) for n in METADATA_OWN},
        "metadata recovery OWN3 source inventory differs")
    a.binding_map(sources)
    transform = boundary_transform_from_frozen_source(a)
    exact(recovery, {"schema": "paper3-boundary-stop-metadata-recovery-v2", "original_plan_path": str(OLD_ERRATUM_PLAN),
        "original_plan_sha256": OLD_ERRATUM_PLAN_SHA, "boundary_transform": transform,
        "old_failure_files_sha256": OLD_FAILURES, "real_smoke_files_sha256": SMOKE_PINS,
        "old_supervisor_failure_preserved": True, "models_or_statistics_restarted": False,
        "automatic_retry": False, "DW0001_STOP_consumption_claimed": False,
        "test_proof_path": str(RECOVERY_PROOF)}, "metadata recovery scope")
    proof = a.bound_json(RECOVERY_PROOF, recovery["test_proof_sha256"])
    exact(proof, {"schema": "paper3-boundary-stop-recovery-test-proof-v1", "all_pass": True,
        "errors": 0, "failures": 0, "skipped": 0, "source_sha256": sources, "boundary_transform": transform,
        "models_statistics_real_publication_or_process_control": False,
        "real_smoke_metadata_readonly_pass": True}, "metadata recovery test proof")
    require(type(proof.get("tests_run")) is int and proof["tests_run"] >= 12, "metadata recovery tests incomplete")
    check_old_failure_chain(a)
    return recovery


def check_recovery_package_sources(a, corrected, ep, expected_sha, erratum):
    recovery = check_recovery_plan(a, ep, expected_sha)
    exact(erratum, {"metadata_recovery": recovery, "old_erratum_and_supervisor_actual_exit_code": 1,
        "old_failed_attempt_success_fabricated": False}, "erratum preserved failure disclosure")
    for filename, digest in recovery["source_sha256"].items():
        a.bound(corrected / "metadata_recovery_source" / Path(filename).name, digest)
    a.bound(corrected / "metadata_recovery_source" / RECOVERY_PROOF.name, recovery["test_proof_sha256"])
    a.bound(corrected / "metadata_recovery_source/ORIGINAL_FAILED_PLAN_002.json", OLD_ERRATUM_PLAN_SHA)
    a.bound(corrected / "erratum_source/ERRATUM_PLAN.json", expected_sha)
    for filename, digest in ERRATUM_PINS.items():
        a.bound(corrected / "erratum_source" / Path(filename).name, digest)
    a.bound(corrected / "erratum_source" / ERRATUM_PROOF.name, ERRATUM_PROOF_SHA)
    expected_sources = set(METADATA_OWN) | {RECOVERY_PROOF.name, "ORIGINAL_FAILED_PLAN_002.json"}
    require({p.name for p in (corrected / "metadata_recovery_source").iterdir()} == expected_sources,
        "metadata recovery copied source set differs")
    expected_failures = set()
    for index, (filename, digest) in enumerate(sorted(OLD_FAILURES.items()), 1):
        name = f"{index:02d}_{Path(filename).name}"
        expected_failures.add(name)
        a.bound(corrected / "preserved_failure_evidence" / name, digest)
    require({p.name for p in (corrected / "preserved_failure_evidence").iterdir()} == expected_failures,
        "preserved failure copy inventory differs")
    return recovery


def check_smoke_boundary_recovery(a, plan, observed):
    certificate = a.bound_json(plan["smoke_certificate_path"], plan["smoke_certificate_sha256"])
    ref = certificate["contract"]
    contract = a.bound_json(ref["path"], ref["sha256"])
    root = safe_relative(RESULTS, contract["run_relative"])
    for relative, digest in SMOKE_PINS.items():
        a.bound(safe_relative(root, relative), digest)
    journals = sorted((root / "journal").glob("*.json"))
    require([p.name for p in journals] == [f"{n:06d}.json" for n in range(1, 6)], "real smoke journal inventory differs")
    actions = ("INITIALIZED", "CLAIMED", "COMPLETED", "RETIRED_AT_BOUNDARY", "RETIRED_AT_BOUNDARY")
    bindings = {"manifest_digest": MANIFEST, "input_bundle_digest": F1,
        "contract_sha256": ref["sha256"], "sidecar_digest": contract["sidecar_digest"]}
    previous = None
    values = []
    for index, path in enumerate(journals, 1):
        digest = a.sha(path)
        value = read(path)
        exact(value, {"schema": "paper3-dynamic-queue-event-v1", "sequence": index,
            "action": actions[index - 1], "previous_sha256": previous, "bindings": bindings}, "smoke journal chain")
        require(observed["evidence_sha256"].get(str(path)) == digest, "observed smoke journal evidence differs")
        values.append(value)
        previous = digest
    claim, done = values[1]["body"], values[2]["body"]
    require(claim["worker_id"] == done["worker_id"] == "DW0001" and
        all(claim[k] == done[k] for k in ("task", "claim_id", "task_digest", "bindings")), "smoke claim/completion ownership differs")
    require(claim["task"] == contract["eligible_tasks"][0] and len(contract["eligible_tasks"]) == 1 and
        done["proof"].get("validated") is True, "smoke task domain/completion differs")
    for index, worker in ((3, "DW0001"), (4, "DW0002")):
        require(values[index]["body"] == {"worker_id": worker, "inflight_killed": False}, "smoke retirement body differs")
    for worker, command_count, event_count in (("DW0001", 2, 1), ("DW0002", 1, 0)):
        directory = root / "workers" / worker
        h = a.sha(directory / "contract.json")
        commands = sorted((directory / "commands").glob("*.json"))
        events = sorted((directory / "events").glob("*.done.json"))
        require([p.name for p in commands] == [f"{n:06d}.json" for n in range(1, command_count + 1)] and
            len(events) == event_count, "real smoke TASK/STOP/DONE inventory differs")
        stop = read(commands[-1])
        require(stop == {"action": "STOP", "contract_sha256": h,
            "reason": "validated trajectory boundary; no inflight termination"}, "real smoke final STOP differs")
        for p in (*commands, *events):
            require(observed["evidence_sha256"].get(str(p)) == a.sha(p), "real command/DONE is not smoke-evidence bound")
        if event_count:
            command = read(commands[0])
            require(command == {"action": "TASK", **claim, "contract_sha256": h}, "real DW1 TASK differs")
            event = read(events[0])
            exact(event, {"schema": "paper3-dynamic-task-done-v1", "task": claim["task"],
                "task_digest": claim["task_digest"], "claim_id": claim["claim_id"], "worker_id": worker,
                "command_sha256": a.sha(commands[0]), "contract_sha256": h,
                "receipt_sha256": done["proof"]["receipt_sha256"], "output_sha256": done["proof"]["output_hash"]}, "real DONE evidence")
    return {"two_retirements_after_completed_task": True, "real_STOP_and_retirement_SHA_verified": True,
        "DW0001_STOP_consumption_claimed": False, "inflight_killed": False}


def check_recovery_exit_contract(start, observation, start_sha, ep, plan_sha):
    recovery = ep["metadata_recovery"]
    sources = recovery["source_sha256"]
    wanted = {"plan_sha256": plan_sha, "helper_sha256": sources[str(METADATA_HELPER)],
        "test_proof_sha256": recovery["test_proof_sha256"],
        "launcher_sha256": sources[str(METADATA_RECOVERY / "root_erratum_launch003.py")],
        "automatic_retry": False, "native_handle_retained_until_wait": True}
    exact(start, {**wanted, "schema": "paper3-root-erratum-recovery-process-start-v1",
        "producer": "ROOT_OWNING_POPEN"}, "recovery root owning start")
    exact(observation, {**wanted, "schema": "paper3-root-erratum-recovery-process-exit-v1",
        "producer": "OWN_ROOT_POPEN_WAIT", "actual_exit_code": 0, "native_exit_code": 0,
        "identity_unchanged": True, "start_receipt_sha256": start_sha}, "recovery root actual exit")
    for key in ("pid", "creation_filetime"):
        require(type(start.get(key)) is int and start[key] > 0 and
            type(observation.get(key)) is int and observation[key] == start[key], "recovery native identity differs: " + key)
    require(isinstance(start.get("image"), str) and isinstance(observation.get("image"), str) and
        Path(start["image"]).resolve() == Path(observation["image"]).resolve() == METADATA_PYTHON.resolve(),
        "recovery native image differs")
    argv = [str(METADATA_PYTHON), "-I", "-S", "-B", str(METADATA_HELPER), "execute", "--plan", str(ERRATUM_PLAN),
        "--plan-sha256", plan_sha]
    require(start.get("cmdargv") == argv and start.get("command_line") == subprocess.list2cmdline(argv),
        "recovery exact native command/argv differs")
    return {"status": "VERIFIED_FROM_ROOT_OWNING_POPEN_AND_RETAINED_NATIVE_EXIT", "actual_exit_code": 0,
        "native_exit_code": 0, "pid": start["pid"], "creation_filetime": start["creation_filetime"],
        "identity_unchanged": True, "native_handle_retained_until_wait": True}


def check_recovery_exit(a, args, ep):
    require(args.recovery_exit_observation and Path(args.recovery_exit_observation).resolve() == ROOT_RECOVERY_EXIT,
        "unexpected root recovery exit observation path")
    require(digest_string(args.recovery_exit_sha256), "explicit root recovery exit SHA required")
    require(digest_string(args.recovery_plan_sha256), "explicit finalized recovery plan SHA required")
    start_sha = a.sha(ROOT_RECOVERY_START)
    start = read(ROOT_RECOVERY_START)
    observation = a.bound_json(ROOT_RECOVERY_EXIT, args.recovery_exit_sha256)
    result = check_recovery_exit_contract(start, observation, start_sha, ep, args.recovery_plan_sha256)
    expected_paths = {"plan_path": str(ERRATUM_PLAN), "helper_path": str(METADATA_HELPER),
        "test_proof_path": str(RECOVERY_PROOF), "launcher_path": str(METADATA_RECOVERY / "root_erratum_launch003.py"),
        "models_or_statistics_restarted": False}
    exact(start, expected_paths, "root recovery launch path/scope")
    exact(observation, expected_paths, "root recovery exit path/scope")
    finish_path = ERRATUM_RECORD / "finish.json"
    exact(observation, {"finish_path": str(finish_path), "finish_sha256": a.sha(finish_path),
        "log_path": str(METADATA_RECOVERY / "ROOT_ERRATUM_RECOVERY_PROCESS_004.log")}, "root recovery legal finish linkage")
    a.bound(observation["log_path"], observation["log_sha256"])
    a.external_allowed.add(str(METADATA_PYTHON.resolve()).casefold())
    a.bound(METADATA_PYTHON, METADATA_PYTHON_SHA)
    producer_start = ERRATUM_RECORD / "start.json"
    a.sha(producer_start)
    exact(read(producer_start), {"schema": "paper3-smoke-count-erratum-start-v1", "pid": start["pid"],
        "plan_sha256": args.recovery_plan_sha256, "models_statistics_executed": False}, "new erratum producer start")
    result["root_start_receipt_sha256"] = start_sha
    result["root_exit_observation_sha256"] = args.recovery_exit_sha256
    result["producer_finish_sha256"] = observation["finish_sha256"]
    return result


def check_delivery(a, plan, stats, stats_receipt, plan_sha, recovery_plan_sha):
    for root in (RECORD, ERRATUM_RECORD):
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
    require(old_draft_sha == H1, "previous legally published root handoff SHA differs")
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
    check_recovery_plan(a, ep, recovery_plan_sha)
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
    check_recovery_package_sources(a, corrected, ep, recovery_plan_sha, erratum)
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
    boundary_evidence = check_smoke_boundary_recovery(a, plan, read(smoke_path))
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
    failures = check_old_failure_chain(a)
    a.checks["delivery"] = {"sequence_native_exit_zero_receipt_verified": True, "statistics_process_exit_zero": True,
        "metadata_recovery_legal_finish_verified": True,
        "reviewed_package_files": len(reviewed_inventory), "first_final_package_files": len(final_inventory),
        "erratum_package_files": len(corrected_inventory), "zip_member_hashes_verified": a.zipped_files_checked,
        "root_archive_chain": [F50, old_draft_sha, corrected_draft_sha], "corrected_reports": corrected_paths,
        "statistics_bytes_preserved": True, "current_handoff": str(REPO / ROOT_HANDOFF), "current_handoff_sha256": corrected_draft_sha}
    a.checks["delivery"]["actual_smoke_worker_metadata"] = smoke_evidence
    a.checks["delivery"]["actual_smoke_boundary_metadata"] = boundary_evidence
    a.checks["delivery"]["preserved_failed_control_attempt"] = failures


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


def check_postpublication_plan_contract(plan, proof):
    exact(plan, {"schema": "paper3-metadata-postpublication-plan-v1", "scope": POST_SCOPE,
        "source_sha256": POST_SOURCE_PINS, "test_proof_path": str(POST_PROOF), "test_proof_sha256": POST_PROOF_SHA,
        "bound_files_sha256": POST_BOUND_FILES, "record_root": str(POST_RECORD),
        "original_metadata_producer_pid": 10108, "original_metadata_producer_actual_exit_code": "NOT_OBSERVED",
        "models_statistics_or_root_publication_executed": False}, "controlled postpublication plan")
    exact(proof, {"schema": "paper3-postpublication-synthetic-proof-v1", "all_pass": True,
        "tests_run": 11, "errors": 0, "failures": 0, "skipped": 0,
        "implementation_sha256": POST_SOURCE_PINS,
        "actual_models_statistics_publication_or_process_control": False}, "controlled postpublication test proof")


def check_postpublication_exit_contract(start, observation, native, certificate, producer_start,
        start_sha, finish_sha, native_sha, plan_sha):
    require(plan_sha == POST_PLAN_SHA, "postpublication finalization plan differs")
    common = {"plan_path": str(POST_PLAN), "plan_sha256": plan_sha, "source_sha256": POST_SOURCE_PINS,
        "automatic_retry": False, "models_statistics_or_root_publication_executed": False,
        "query_handle_retained": True, "helper_path": str(POST_FINALIZATION / "postpublication_finalize.py"),
        "helper_sha256": POST_SOURCE_PINS[str(POST_FINALIZATION / "postpublication_finalize.py")]}
    exact(start, {**common, "schema": "paper3-postpublication-process-start-v1",
        "producer": "ROOT_OWNING_POPEN"}, "new finalization native start")
    exact(observation, {**common, "schema": "paper3-postpublication-process-exit-v1",
        "producer": "ROOT_OWNING_POPEN_WAIT", "actual_exit_code": 0, "native_exit_code": 0,
        "identity_unchanged": True, "start_receipt_sha256": start_sha,
        "native_observation_sha256": native_sha, "finish_path": str(POST_RECORD / "finish.json"),
        "finish_sha256": finish_sha, "log_path": str(POST_FINALIZATION / "POSTPUBLICATION_PROCESS_001.log")},
        "new finalization owning/native zero exit")
    exact(native, {"schema": "paper3-postpublication-native-exit-observation-v1",
        "producer": "ROOT_OWNING_POPEN_WAIT", "plan_sha256": plan_sha,
        "actual_exit_code": 0, "native_exit_code": 0}, "durable new native exit")
    pid, creation = start.get("pid"), start.get("creation_filetime")
    require(type(pid) is int and pid > 0 and type(creation) is int and creation > 0,
        "new finalization positive native PID/FILETIME required")
    argv = [str(METADATA_PYTHON), "-I", "-S", "-B", str(POST_FINALIZATION / "postpublication_finalize.py"),
        "execute", "--plan", str(POST_PLAN), "--plan-sha256", plan_sha]
    require(start.get("cmdargv") == observation.get("cmdargv") == argv,
        "new finalization command argv differs")
    for label, item in (("start", start), ("exit", observation), ("native", native)):
        exact(item, {"pid": pid, "creation_filetime": creation,
            "command_line": subprocess.list2cmdline(argv)}, "new finalization " + label + " identity")
        require(isinstance(item.get("image"), str) and Path(item["image"]).resolve() == METADATA_PYTHON.resolve(),
            "new finalization captured launch image differs: " + label)
    exact(producer_start, {"schema": "paper3-postpublication-finalization-start-v1", "pid": pid,
        "plan_sha256": plan_sha}, "new artifact certification start")
    exact(certificate, {"schema": "paper3-metadata-postpublication-artifact-finalization-v1", "status": "COMPLETED",
        "scope": POST_SCOPE, "plan_sha256": plan_sha, "pid": pid, "source_sha256": POST_SOURCE_PINS,
        "original_metadata_producer_pid": 10108, "original_metadata_producer_actual_exit_code": "NOT_OBSERVED",
        "root_exit_observer_failed": True, "original_observer_tool_actual_exit_code": 1,
        "history_all_process_exits_verified": False, "original_exit_zero_contract_satisfied": False,
        "scientific_acceptance": "NOT_PERFORMED_BY_THIS_METADATA_FINALIZER",
        "models_statistics_or_root_publication_executed": False,
        "producer_plan_sha256": OLD_METADATA_PLAN_SHA, "producer_finish_sha256": OLD_METADATA_FINISH_SHA,
        "observer_failure_sha256": OLD_ROOT_OBSERVER_FAILURE_SHA,
        "package": str(POST_PACKAGE), "package_manifest_sha256": PUBLISHED_ERRATUM_MANIFEST_SHA,
        "zip": str(POST_PACKAGE.with_suffix(".zip")), "zip_sha256": PUBLISHED_ERRATUM_ZIP_SHA,
        "root_handoff_sha256": PUBLISHED_H2, "statistics_manifest_sha256": PUBLISHED_STATISTICS_MANIFEST_SHA,
        "statistics_execution_receipt_sha256": PUBLISHED_STATISTICS_RECEIPT_SHA,
        "statistics_bytes_unchanged": True, "reports_inverse_bytes_preserved": True}, "new artifact finalization certificate")
    return {"actual_exit_code": 0, "native_exit_code": 0, "identity_unchanged": True,
        "query_handle_retained": True, "pid": pid, "creation_filetime": creation,
        "plan_sha256": plan_sha, "start_receipt_sha256": start_sha, "finish_sha256": finish_sha,
        "native_observation_sha256": native_sha,
        "acceptance_scope": "scientific_artifacts_and_new_metadata_finalization",
        "metadata_original_producer_exit": "NOT_OBSERVED; ROOT_EXIT_OBSERVER_FAILED",
        "history_all_process_exits_verified": False, "old_metadata_process_exit_zero_verified": False}


def check_postpublication_finalization(a, args, ep):
    require(args.finalization_plan_sha256 == POST_PLAN_SHA, "only the frozen postpublication plan is accepted")
    require(Path(args.finalization_exit_observation).resolve() == POST_EXIT.resolve(),
        "finalization exit observation must be the owned fixed path")
    require(digest_string(args.finalization_exit_sha256), "explicit postpublication actual exit SHA required")
    require(not (POST_RECORD / "stopped.json").exists(), "new artifact finalization stopped")
    plan = a.bound_json(POST_PLAN, POST_PLAN_SHA)
    proof = a.bound_json(POST_PROOF, POST_PROOF_SHA)
    check_postpublication_plan_contract(plan, proof)
    a.binding_map(POST_SOURCE_PINS)
    a.binding_map(POST_BOUND_FILES)
    a.external_allowed.add(str(METADATA_PYTHON.resolve()).casefold())
    a.bound(METADATA_PYTHON, METADATA_PYTHON_SHA)
    observation = a.bound_json(POST_EXIT, args.finalization_exit_sha256)
    for key in ("start_receipt_sha256", "finish_sha256", "native_observation_sha256", "log_sha256"):
        require(digest_string(observation.get(key)), "finalizer exit receipt digest invalid: " + key)
    start = a.bound_json(POST_START, observation["start_receipt_sha256"])
    native = a.bound_json(POST_NATIVE, observation["native_observation_sha256"])
    certificate = a.bound_json(POST_RECORD / "finish.json", observation["finish_sha256"])
    producer_start_path = POST_RECORD / "start.json"
    a.sha(producer_start_path)
    producer_start = read(producer_start_path)
    result = check_postpublication_exit_contract(start, observation, native, certificate, producer_start,
        observation["start_receipt_sha256"], observation["finish_sha256"], observation["native_observation_sha256"], POST_PLAN_SHA)
    a.bound(POST_FINALIZATION / "POSTPUBLICATION_PROCESS_001.log", observation["log_sha256"])
    package_manifest = a.bound_json(POST_PACKAGE / "ERRATUM_MANIFEST.json", PUBLISHED_ERRATUM_MANIFEST_SHA)
    package_files = dict(package_manifest["package_files_sha256"])
    package_files["ERRATUM_MANIFEST.json"] = PUBLISHED_ERRATUM_MANIFEST_SHA
    package_files["ERRATUM_MANIFEST.json.sha256"] = a.sha(POST_PACKAGE / "ERRATUM_MANIFEST.json.sha256")
    exact(certificate, {"package_file_count": len(package_files), "package_files_sha256": package_files},
        "new certificate exact published inventory")
    stats_manifest = a.bound_json(STATS / "statistics_manifest.json", PUBLISHED_STATISTICS_MANIFEST_SHA)
    stats_files = {str(STATS / name): digest for name, digest in stats_manifest["outputs_sha256"].items()}
    require(len(stats_files) == 16, "new certificate must bind all 16 saved statistics outputs")
    exact(certificate, {"statistics_files_sha256": stats_files}, "new certificate unchanged saved statistics")
    a.binding_map(stats_files)
    a.binding_map({str(safe_relative(POST_PACKAGE, name)): digest for name, digest in package_files.items()})
    require(POST_PACKAGE.with_suffix(".zip").stat().st_size == PUBLISHED_ERRATUM_ZIP_BYTES,
        "new certificate exact published ZIP size differs")
    result.update(artifact_certificate_schema=certificate["schema"], artifact_inventory_exact=True,
        all_saved_statistics_bound=True, independent_full_scientific_checks_not_waived=True,
        root_exit_sha256=args.finalization_exit_sha256, test_proof_sha256=POST_PROOF_SHA)
    return result


def check_frozen_v3_acceptance_preservation(a):
    """All V3 science, metadata evidence and published-package checks persist."""
    frozen = a.bound(FROZEN_V3_AUDITOR, FROZEN_V3_AUDITOR_SHA).read_bytes()
    require(hashlib.sha256(frozen).hexdigest() == FROZEN_V3_AUDITOR_SHA, "verified V3 source bytes changed")
    path = Path(__file__)
    expected = a.sha(path)
    current = path.read_bytes()
    require(hashlib.sha256(current).hexdigest() == expected, "V4 source bytes changed during source comparison")
    def nodes(payload):
        text = payload.decode("utf-8")
        return {n.name: ast.get_source_segment(text, n) for n in ast.parse(text).body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    old, new = nodes(frozen), nodes(current)
    unchanged = ("Auditor", "read", "exact", "safe_relative", "canonical", "stem", "check_raw", "check_statistics",
        "check_publication", "check_erratum_proof", "check_smoke_worker_metadata", "metadata_contract_preflight",
        "check_scientific_auditor_preservation", "boundary_transform_from_frozen_source", "check_old_failure_chain",
        "check_recovery_plan", "check_recovery_package_sources", "check_smoke_boundary_recovery", "check_delivery")
    require(all(old[name] == new[name] for name in unchanged), "frozen V3 scientific/artifact/evidence checks changed")
    require(old["run"].split("    recovery_exit = ")[0] == new["run"].split("    finalization_exit = ")[0],
        "frozen V3 full science and artifact run prefix changed")
    return {"frozen_v3_auditor_sha256": FROZEN_V3_AUDITOR_SHA, "unchanged_functions": list(unchanged),
        "full_scientific_and_published_artifact_prefix_byte_identical": True,
        "current_control_chain_only_replaced_with_new_readonly_artifact_finalization": True}


def check_original_metadata_observer_failure(a, ep):
    require(not ROOT_RECOVERY_EXIT.exists(), "unobserved historical metadata exit was retroactively filled")
    start = a.bound_json(ROOT_RECOVERY_START, OLD_METADATA_START_SHA)
    recovery = ep["metadata_recovery"]
    exact(start, {"schema": "paper3-root-erratum-recovery-process-start-v1", "producer": "ROOT_OWNING_POPEN",
        "pid": 10108, "creation_filetime": 134361042783635120, "plan_path": str(ERRATUM_PLAN),
        "plan_sha256": OLD_METADATA_PLAN_SHA, "helper_path": str(METADATA_HELPER),
        "helper_sha256": recovery["source_sha256"][str(METADATA_HELPER)],
        "test_proof_path": str(RECOVERY_PROOF), "test_proof_sha256": recovery["test_proof_sha256"],
        "launcher_path": str(METADATA_RECOVERY / "root_erratum_launch003.py"),
        "launcher_sha256": recovery["source_sha256"][str(METADATA_RECOVERY / "root_erratum_launch003.py")],
        "models_or_statistics_restarted": False, "automatic_retry": False,
        "native_handle_retained_until_wait": True}, "original metadata native launch")
    argv = [str(METADATA_PYTHON), "-I", "-S", "-B", str(METADATA_HELPER), "execute", "--plan", str(ERRATUM_PLAN),
        "--plan-sha256", OLD_METADATA_PLAN_SHA]
    require(start["cmdargv"] == argv and start["command_line"] == subprocess.list2cmdline(argv) and
        Path(start["image"]).resolve() == METADATA_PYTHON.resolve(), "original metadata native launch command/image differs")
    producer_start = ERRATUM_RECORD / "start.json"
    a.sha(producer_start)
    exact(read(producer_start), {"schema": "paper3-smoke-count-erratum-start-v1", "pid": 10108,
        "plan_sha256": OLD_METADATA_PLAN_SHA, "models_statistics_executed": False}, "original metadata producer start")
    finish = a.bound_json(ERRATUM_RECORD / "finish.json", OLD_METADATA_FINISH_SHA)
    exact(finish, {"status": "SMOKE_COUNT_METADATA_ERRATUM_COMPLETED", "statistics_bytes_unchanged": True,
        "root_handoff_sha256": PUBLISHED_H2, "zip_sha256": PUBLISHED_ERRATUM_ZIP_SHA}, "original metadata published finish")
    failure = a.bound_json(OLD_ROOT_OBSERVER_FAILURE, OLD_ROOT_OBSERVER_FAILURE_SHA)
    exact(failure, {"schema": "paper3-root-metadata-exit-observer-failure-v1",
        "status": "EXIT_OBSERVER_FAILED_AFTER_LEGAL_PUBLICATION", "producer": "EXEC_COMMAND_TOOL_EXIT_OBSERVATION",
        "actual_tool_exit_code": 1, "tool_chunk_id": "27979c", "original_metadata_producer_pid": 10108,
        "original_metadata_producer_actual_exit_code": "NOT_OBSERVED", "actual_exit_zero_reconstructed": False,
        "producer_finish_path": str(ERRATUM_RECORD / "finish.json"), "producer_finish_sha256": OLD_METADATA_FINISH_SHA,
        "start_receipt_path": str(ROOT_RECOVERY_START), "start_receipt_sha256": OLD_METADATA_START_SHA,
        "producer_legal_finish_verified": True, "old_exit_receipt_written": False,
        "scientific_or_report_bytes_modified_by_observer": False,
        "source_path": str(METADATA_RECOVERY / "root_erratum_launch003.py"),
        "observer_source_sha256": recovery["source_sha256"][str(METADATA_RECOVERY / "root_erratum_launch003.py")],
        "failure": "RuntimeError: retained native image query failed"}, "preserved metadata exit observer failure")
    return {"original_metadata_producer_pid": 10108,
        "metadata_original_producer_exit": "NOT_OBSERVED; ROOT_EXIT_OBSERVER_FAILED",
        "root_exit_observer_failed": True, "original_observer_tool_actual_exit_code": 1,
        "history_all_process_exits_verified": False, "old_metadata_process_exit_zero_verified": False,
        "actual_exit_zero_reconstructed": False, "legal_publication_finish_verified": True,
        "original_metadata_finish_sha256": OLD_METADATA_FINISH_SHA,
        "root_exit_observer_failure_sha256": OLD_ROOT_OBSERVER_FAILURE_SHA}


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
    check_delivery(a, plan, stats, receipt, args.expected_plan_sha256, args.recovery_plan_sha256)
    a.checks["scientific_auditor_preservation"] = check_scientific_auditor_preservation(a)
    ep = a.bound_json(ERRATUM_PLAN, args.recovery_plan_sha256)
    finalization_exit = check_postpublication_finalization(a, args, ep)
    a.checks["metadata_postpublication_finalization_process"] = finalization_exit
    a.checks["original_metadata_exit_observer_failure"] = check_original_metadata_observer_failure(a, ep)
    a.checks["frozen_v3_auditor_preservation"] = check_frozen_v3_acceptance_preservation(a)
    a.stable()
    return {"schema": "paper3-independent-final-readonly-acceptance-v4", "status": "PASS",
        "acceptance_scope": "scientific_artifacts_and_new_metadata_finalization",
        "scientific_and_artifact_acceptance": "PASS", "history_all_process_exits_verified": False,
        "metadata_original_producer_exit": "NOT_OBSERVED; ROOT_EXIT_OBSERVER_FAILED",
        "old_metadata_process_exit_zero_verified": False,
        "observed_utc": utc(), "repository": str(REPO), "results": str(RESULTS), "auditor_sha256": a.sha(Path(__file__)),
        "manifest_digest": MANIFEST, "input_bundle_digest": F1, "expected_plan_sha256": args.expected_plan_sha256,
        "full_gate_sha256": GATE_SHA, "full_certificate_sha256": CERT_SHA, "checks": a.checks,
        "old_supervisor_actual_exit_code": 1, "old_erratum_actual_exit_code": 1,
        "recovery_plan_sha256": args.recovery_plan_sha256,
        "postpublication_finalization_plan_sha256": args.finalization_plan_sha256,
        "metadata_postpublication_finalization_os_exit": finalization_exit,
        "unique_files_hashed": len(a.expected), "file_bytes_hashed": a.bytes_hashed,
        "original_protected_files_verified": 2535, "environment_bound_files_verified": len(manifest["environment"]["bound_files_sha256"]),
        "F1_bound_files_verified": len(manifest["input_files_sha256"]), "no_models_generators_or_statistics_executed": True,
        "no_files_written": True, "no_new_endpoints_bootstrap_or_CI_computed": True,
        "historical_environment_reproduced": False, "new_unseen_heldout_claimed": False,
        "manuscript_automatically_frozen": False,
        "observation_scope": "Saved science, pairing fields, statistics dimensions, exact package/ZIP bytes and publication chain plus new read-only artifact finalization exit zero. Original metadata producer OS exit remains NOT_OBSERVED after its observer failed; historical zero is not reconstructed."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-plan-sha256", default=PLAN_SHA)
    parser.add_argument("--recovery-plan-sha256")
    parser.add_argument("--finalization-plan-sha256")
    parser.add_argument("--finalization-exit-observation", default=str(POST_EXIT))
    parser.add_argument("--finalization-exit-sha256")
    parser.add_argument("--metadata-contract-preflight", action="store_true",
        help="Read receipt JSON contracts and one raw CSV sample; never run full acceptance or hash all data/environment")
    args = parser.parse_args()
    try:
        if not args.metadata_contract_preflight:
            require(digest_string(args.recovery_plan_sha256), "explicit finalized recovery plan SHA required")
            require(args.recovery_plan_sha256 == OLD_METADATA_PLAN_SHA, "published metadata plan binding differs")
            require(digest_string(args.finalization_plan_sha256), "explicit finalized postpublication plan SHA required")
            require(digest_string(args.finalization_exit_sha256), "explicit root postpublication exit SHA required")
        result = metadata_contract_preflight(args) if args.metadata_contract_preflight else run(args)
    except Exception as error:
        print(json.dumps({"schema": "paper3-independent-final-readonly-acceptance-v4", "status": "BLOCKED",
            "observed_utc": utc(), "error_type": type(error).__name__, "message": str(error),
            "no_files_written": True, "no_models_generators_or_statistics_executed": True}, sort_keys=True), flush=True)
        return 1
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
