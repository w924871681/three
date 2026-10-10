"""Build NEW archive prose from saved evidence; never execute models/statistics."""
from pathlib import Path
import csv
import hashlib
import json

R = Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
B = R / "verification/paper3_canonical_inputs"
OUT = Path(__file__).resolve().parent
E = R / "handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001"
RESULT = R / "results/p7_7_integrity_replication_batch20_env_v3"
ENV = B / "model_env_recovery_v1_20261009"
V4 = B / "replication_dynamic_delivery_recovery_v4"
POST = B / "replication_metadata_postpublication_finalize_v1"

def read(p):
    return json.loads(p.read_text(encoding="utf-8"))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def write_new(name, content):
    with (OUT / name).open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)

entries = []
by_path = {}

def evidence(p, role, expected=None, copy=True):
    p = p.resolve()
    if p in by_path:
        return by_path[p]
    digest = sha(p)
    if expected is not None and digest != expected:
        raise AssertionError(f"Evidence conflict: {p}")
    item = {"source_path": str(p), "repository_relative_path": p.relative_to(R).as_posix(),
            "sha256": digest, "size_bytes": p.stat().st_size, "role": role,
            "recommended_archive_copy": copy, "verification_scope": "CURRENT_SELECTED_EVIDENCE_BYTES"}
    entries.append(item)
    by_path[p] = item
    return item

def ref(p):
    item = by_path[p.resolve()]
    return f"[{p.name}](<{p.as_posix()}>) (SHA256 `{item['sha256']}`)"

manifest = read(RESULT / "provenance_manifest.json")
environment = manifest["environment"]
acceptance = read(V4 / "FINAL_READONLY_ACCEPTANCE_004.json")
assert acceptance["status"] == "PASS"
assert acceptance["scientific_and_artifact_acceptance"] == "PASS"
assert acceptance["original_protected_files_verified"] == 2535
assert acceptance["environment_bound_files_verified"] == 13192
assert acceptance["checks"]["raw_matrix"]["trajectories"] == 1200
assert acceptance["checks"]["raw_matrix"]["paired_groups"] == 240
assert read(V4 / "FINAL_READONLY_ACCEPTANCE_ACTUAL_EXIT_004.json")["actual_exit_code"] == 0
assert read(POST / "POSTPUBLICATION_PROCESS_EXIT_001.json")["actual_exit_code"] == 0

primary = [
    (RESULT / "provenance_manifest.json", "Pre-execution frozen provenance, exact runtime, scientific/source/model/config/input bindings", "c9277ed25b9c4e6df0b2ecfffeeefa3fdaa087ba4f326de828513402d5d20076"),
    (RESULT / "initial_state_manifest.json", "Completed 60 center-seed initial reference certification", None),
    (RESULT / "input_reference_manifest.json", "Canonical F1 input references", None),
    (RESULT / "full_experiment_integrity_gate.json", "Completed full 1200 trajectories / 240 paired groups / 24-stage gate", "a33555e7f6083229aff520fe6e0a8f6ad11b2ef468cda3f8929be4cbe9240a97"),
    (V4 / "FINAL_READONLY_ACCEPTANCE_004.json", "Previously completed independent full scientific/artifact acceptance; reuse without rerunning", None),
    (V4 / "FINAL_READONLY_ACCEPTANCE_ACTUAL_EXIT_004.json", "Root owning-Popen actual exit 0 for auditor PID 12964", None),
    (V4 / "FINAL_READONLY_ACCEPTANCE_PROCESS_START_004.json", "Root auditor identity/start evidence", None),
    (V4 / "final_readonly_acceptance.py", "Exact source of reused full auditor", acceptance["auditor_sha256"]),
    (POST / "POSTPUBLICATION_PROCESS_EXIT_001.json", "New read-only artifact finalizer PID 30796 owning/native exit 0", "8e584d5929534d0eb299fcad65490c31f3ca8ade4fe41a1efc83dc67f4a250d8"),
    (POST / "finalize001/finish.json", "Postpublication artifact finalization certificate; no reconstructed historical exit", "38e9e8a08d6a2ad7f52e6a07665f67d670b3c4d7f9397b8f99310efd7396b915"),
    (B / "replication_dynamic_delivery_erratum_recovery_v2/ROOT_EXIT_OBSERVER_FAILURE_004.json", "Preserved observer failure actual 1; producer PID 10108 exit NOT_OBSERVED", "92de2eec50b9be2200eb02296b64e45ff927452d6eb4911ec577e24ebfa4f5c7"),
    (E / "ERRATUM_MANIFEST.json", "COMPLETED superseding manifest binding current six corrected reports and root H2", "2ada566465c1fe4f2bf4b6db0da22d8404cd6a0bdf8c7870820bb27e4df88bd8"),
    (E / "ERRATUM.json", "Certified metadata-only smoke count erratum; preserved original statistics and failure evidence", "6af0a15166cd756fbd6b135a31caacfd6857ee9a8452ad080126fe7adcb9baf1"),
    (E / "SMOKE_PROCESS_COUNT_EVIDENCE.json", "Two started workers / one trajectory-owning worker", None),
    (E / "root_publication/PUBLICATION_RECEIPT.json", "Legal archived H1 to H2 root publication", "cabd2f16e8fdf5827da840f72464e4aeb292bf05565a3f2e3c9c0162692ae19f"),
    (E / "original_v1_final_package/reviewed_delivery/DELIVERY_MANIFEST.json", "Preserved original COMPLETED delivery manifest binding the original report bytes", "aa5dae819d88ef95614276ffe79b2633a186c099a41709f704b6702835ae996b"),
    (RESULT / "statistics_batch20_env_v3/statistics_execution_receipt.json", "Actual saved statistics execution and input/output bindings", "82585cf06c15e2bebc2d37bea90ccb9b6f24aa78745c00f6fd3378a0a0742dec"),
]
for p, role, expected in primary:
    evidence(p, role, expected)

erratum_manifest = read(E / "ERRATUM_MANIFEST.json")
report_names = ["EXECUTION_SUMMARY.md", "INPUT_PARITY_AUDIT.md", "EXPERIMENT_INTEGRITY_AUDIT.md",
                "CORRECTED_FINAL_STATISTICS.md", "ORIGINAL_VS_REPLICATION_COMPARISON.md", "SCIENTIFIC_FREEZE_DECISION.md"]
for n in report_names:
    p = E / "corrected_reports" / n
    p.read_text(encoding="utf-8")
    evidence(p, "Current formal corrected report, preserve exact bytes", erratum_manifest["package_files_sha256"]["corrected_reports/" + n])

source_names = ["configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json", "configs/P7_6B_FROZEN_PROTOCOL.json",
                "configs/P7_7A2_INTEGRATION_DECISION.json", "configs/p7_2_selected_action_params.json",
                "configs/center_splits.json", "configs/p3_mismatch_v2_frozen.json", "configs/requirements_frozen.txt",
                "core/p6.py", "core/p7.py", "scripts/run_p7_7_final.py",
                "reports/P7_7A2_BRANCH_B_INTEGRATION_SPEC.md", "reports/P7_7A2_RECOVERABILITY_ESCALATION_INTEGRATION_AUDIT.md",
                "reports/P7_7_FINAL_LIFECYCLE_PROTOCOL.md", "artifacts/p3_model_bank_manifest.json",
                "artifacts/p3_2_source_bank/p3_mismatch_v2_r3/source_training_manifest.json",
                "artifacts/p7_6b_A1_scaler.json", "audits/P7_6B_FINAL_SCIENTIFIC_AUDIT.json",
                "audits/P7_2_FINAL_CALIBRATION_FREEZE.json", "PAPER3_CANONICAL_INPUT_VERIFICATION_PLAN.md",
                "PAPER3_SINGLE_GROUP_INTEGRITY_FORENSIC_REPORT.md"]
pins = {}
for key in ("adapter_source_pins", "critical_files_sha256", "source_bindings_sha256", "stage_b_source_pins"):
    pins.update(manifest[key])
for n in source_names:
    evidence(R / n, "Frozen method, label, protocol, source-bank or forensic source", pins.get(n))
stats_source = B / "replication_statistics_batch20_env_v3/statistics.py"
evidence(stats_source, "Frozen statistical aggregation, diagnostic masks and joint bootstrap implementation", "5ccda537c83bf88f7531eeee7c9b4b82a55b23f4ba81b3c031b978ac8375e33c")

runtime = read(ENV / "MODEL_RUNTIME_SPEC.json")
native = read(ENV / "NATIVE_COMPATIBILITY_TEST_RECEIPT_ATTEMPT002.json")
assert native["status"] == "PASS"
for name in ["MODEL_RUNTIME_SPEC.json", "MODEL_ENVIRONMENT_RECOVERY_RECEIPT.json", "MODEL_ENVIRONMENT_RECOVERY_AND_COMPATIBILITY_REPORT.md",
             "requirements_runtime_exact_freeze.txt", "WHEELHOUSE_SOURCE_MANIFEST.json"]:
    evidence(ENV / name, "Exact controlled replication runtime and dependency provenance")
for name, expected in runtime["installation_evidence_files_sha256"].items():
    evidence(Path(name), "Saved environment installation, native-copy, compatibility or file-inventory evidence", expected)
stageb = Path(native["stage_b_numpy_file_parity"]["source_manifest"])
evidence(stageb, "Saved Stage-B input generation environment; 772 NumPy/native files parity checked before model execution",
         native["stage_b_numpy_file_parity"]["source_manifest_sha256"])

exec_sources = [
    (RESULT / "execution/full/A_FULL_0001/failure.json", "Unobserved original full attempt exit cause and code remain NOT_VERIFIED"),
    (B / "replication_dynamic_takeover_v1/activation001/quiescence/actual_termination_evidence.json", "Authorized static full_002 intentional cutover; not success"),
    (B / "replication_dynamic_takeover_v1/activation001/real_model_bridge_smoke_certificate.json", "Real two-worker, one-trajectory smoke certificate"),
    (B / "replication_dynamic_takeover_v1/activation001/smoke_coordinator_exit.json", "Observed bridge smoke coordinator exit zero"),
    (B / "replication_dynamic_takeover_v1/activation001/full_contract.json", "Dynamic full contract retaining 332 and requiring 868 new trajectories"),
    (B / "replication_dynamic_takeover_v1/activation001/full_coordinator_exit.json", "Observed dynamic full coordinator exit zero"),
]
for p, role in exec_sources:
    evidence(p, role)

binary_index = [{"source_path": str(R / name), "sha256": pins.get(name) or manifest["critical_files_sha256"].get(name),
                 "role": "Frozen binary model/estimator binding; indexed only, not recopied or rehashed in this prose task",
                 "recommended_archive_copy": False, "verification_scope": "PREVIOUS_V4_FULL_ACCEPTANCE_AND_FROZEN_MANIFEST"}
                for name in manifest["source_checkpoint_files"] + ["artifacts/p7_6b_A1_estimator.pt"]]
assert all(x["sha256"] for x in binary_index)

claim = f"""# Scientific Claim Boundary — Paper 3 Final Evidence Archive

Paper: *Bounded Maintenance Recoverability for Selective Lifecycle Escalation of Digital-Twin Models*.

This is a scientific-review boundary document for the saved **integrity-correction replication**. It does not amend frozen algorithms, labels, thresholds, estimators, centers or statistical protocols. It does not freeze Sections 3–4, the complete manuscript, deployment validity or submission readiness.

## Prior verification reused

The completed independent v4 acceptance inspected the complete 1200 trajectories, 240 five-method groups and 28,800 stage records; verified 2535 protected original files and 13,192 runtime-bound files; and checked saved statistics and delivery bytes. This prose task reuses that actual completed audit rather than repeating the full scan. Its scope is scientific artifacts and new metadata finalization, not a claim that every historical process exit is known. Evidence: {ref(V4 / 'FINAL_READONLY_ACCEPTANCE_004.json')}; actual exit 0: {ref(V4 / 'FINAL_READONLY_ACCEPTANCE_ACTUAL_EXIT_004.json')}.

## Mathematical and operational objects must remain distinct

| Object or rule | Supported interpretation | Claim not established by the saved experiment |
|---|---|---|
| C1 theoretical maintenance recoverability | A quantity defined for the paper's theoretical maintenance policy class, horizon and resource assumptions | Identity with a finite, one-shot empirical reference policy set |
| Finite reference label `R_B50` | Frozen threshold minus the best observed offline horizon loss among the fixed P0/P10/P20/P50 reference procedures; effective horizon `H_t = min(4, 25-t)` | Exhaustive optimization over every policy in the theoretical C1 class; proof of absolute inability to maintain |
| A1 supervised target and online score | A1 is trained against normalized reference evidence `R_B50/S_m`; online inference is a prediction from same-identity causal response features | Equality of a predicted score to its supervised label, the true finite reference margin or the theoretical recoverability quantity |
| Positive identity-held scale `S_m` | The frozen scale is the floored median of 104 errors from the permitted 200-observation deployment reference; positive scaling preserves the sign of the exact label | Guaranteed sign agreement for an imperfect learned prediction |
| `q < 0` (negative A1 operational score) | Makes the fixed-bank RI search admissible under the frozen online rule; the eventual action still follows feasibility, costs, comparison and fallback | A theorem that current-model maintenance is impossible; a requirement to perform RI |
| 50 candidate updates | Exactly 50 frozen adaptation updates for each feasible candidate; a local per-candidate allowance | A total global search budget of 50 updates across all candidates, stages and probe work |

The frozen online implementation and label construction are evidenced by {ref(R / 'core/p6.py')}, {ref(R / 'core/p7.py')} and {ref(R / 'configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json')}. The current corrected scientific decision explicitly retains the unresolved theoretical/empirical/online distinction: {ref(E / 'corrected_reports/SCIENTIFIC_FREEZE_DECISION.md')}. Earlier integration text's use of “unrecoverable” at the zero boundary must not be promoted into proof that a learned online negative score establishes theoretical nonrecoverability. This archive states the boundary; it does not silently rewrite the core definition.

## Service-loss evidence and its inference scope

The saved primary endpoint is mean lifecycle service loss: stage mean within trajectory, then seed/scenario mean within each center, then arithmetic mean over 20 centers. The frozen joint paired bootstrap uses 4000 resamples, seed 2904 and shared resampled center indices across all methods; the observed contrast uses original center means, not the mean of bootstrap replicates.

| Contrast | Observed Proposed-minus-baseline difference | Saved 95% percentile interval | Permitted statement |
|---|---:|---|---|
| P7.7 − B0 | -0.0036641548764590783 | [-0.004573827822422219, -0.0028134015487948244] | Lower mean service loss under this fixed protocol and interval procedure |
| P7.7 − B1 | -0.0004013360535383174 | [-0.0005435194434220294, -0.00027324824378676267] | Lower mean service loss under this fixed protocol and interval procedure |
| P7.7 − B2 | -0.0019432976134592331 | [-0.0022800258030189167, -0.001616486006572207] | Lower mean service loss under this fixed protocol and interval procedure |
| P7.7 − B8 | +0.000028016915328205657 | [-0.00000018594825329880642, +0.00008423669423791578] | The interval crosses zero; superiority is not established |

Thus Proposed significantly lowers service loss relative to B0/B1/B2 in the sense of these specified 95% bootstrap intervals excluding zero. This is not an additional multiplicity-adjusted familywise claim. The B8 point difference is slightly adverse and its interval crosses zero. **No Proposed superiority over B8 and no statistical equivalence or noninferiority are established.** No equivalence margin or equivalence test is introduced after observing the results.

All four scenarios C0/C1/C3/C4 remain reportable. Overall contrasts must not be presented as a win in every scenario: B1 has lower observed loss than P7.7 in C0 and C1. All adverse and zero-crossing results are retained. Numerical evidence: {ref(E / 'corrected_reports/CORRECTED_FINAL_STATISTICS.md')}; statistical source: {ref(stats_source)}; actual saved receipt: {ref(RESULT / 'statistics_batch20_env_v3/statistics_execution_receipt.json')}.

## Search workload, recorded time and costs

P7.7 records 17,428 feasible candidates and 871,400 charged search updates; B8 records 53,280 candidates and 2,664,000 updates. Candidate counts and the `50 × count` charged update measure show reduced recorded search workload. They do not alone establish a corresponding end-to-end wall-clock, energy, financial or deployment cost improvement.

The saved totals are P7.7 `decision_runtime_actual_s = 15102.04218449854` and B8 `34280.914582599944`. The saved standalone-estimate totals happen to equal these recorded totals in this run. They remain semantically separate columns. Actual decision timers attribute work under the implemented execution/cache policy; standalone estimates reconstruct a different accounting convention. Neither is a dedicated controlled end-to-end benchmark including all initialization, loading, resource waiting, validation and packaging. The action cost ratio 10 and event penalties also remain model decision parameters, not measured hardware cost. See `core/p7.py` timer attribution and the corrected statistics report above.

## Missed escalation remains a method limitation

The frozen offline diagnostic denominator is **5760 Proposed stage records** (240 trajectories × 24 stages), not the number of open gates, RI actions or negative labels. “Missed escalation” is `action != 'ri' and R_B50 < 0`: 2100/5760 = 0.3645833333333333. “Unnecessary RI” is `action == 'ri' and not (R_B50 < 0)`: 12/5760 = 0.0020833333333333333. The labels are finite offline reference diagnostics, evaluated after decision sealing; they are not online inputs or ground-truth counterfactual deployment outcomes. In particular, missed escalation is not exclusively a closed-gate error because RI may be admissible but rejected by costs, feasibility or fallback. The four stored diagnostic masks are potentially overlapping and nonexhaustive and must not be presented as an exhaustive confusion matrix. This observed missed-escalation rate remains a material limitation.

## Population, environment and execution scope

This uses the already observed canonical F1 batch20 population in a controlled corrective replication. It is not a previously unseen held-out experiment. Historical complete runtime/numerical equivalence remains **NOT_VERIFIED**. Input/initial-state/deployment parity does not imply model outputs are invariant bit for bit under every worker schedule or Torch RNG history. Differences from the original mixed F/S population cannot identify the separate causal contributions of materialization, runtime and stochastic execution.

Bridge smoke started two workers; only DW0001 completed its one prespecified B1 trajectory and DW0002 received no TASK. Both saved worker exits are zero. A_FULL_0001's lost terminal cause/code remain NOT_VERIFIED; A_FULL_0002's intentional cutover remains an interruption. The later metadata producer PID 10108 has exit **NOT_OBSERVED** after its observer failed; new read-only finalizer PID 30796 and final v4 auditor PID 12964 have their own actual exit-0 receipts. Their success does not reconstruct PID 10108's historical exit. These boundaries are preserved in `SOURCE_ENVIRONMENT_PROVENANCE.md` and its indexed evidence.
"""

versions = "\n".join(f"| `{k}` | `{v}` |" for k, v in sorted(environment["exact_versions"].items()))
provenance = f"""# Source and Environment Provenance — Paper 3 Final Evidence Archive

All statements below come from saved local manifests, runtime receipts, frozen source and the current corrected reports. This archive preparation imported no scientific package and launched no model, generator, training or statistical execution. Selected evidence documents are checked against their stored SHA256 bindings; the already completed v4 full environment/raw audit is reused.

## Current report authority and legal publication chain

The preserved original COMPLETED `DELIVERY_MANIFEST.json` binds the original results reports: {ref(E / 'original_v1_final_package/reviewed_delivery/DELIVERY_MANIFEST.json')}. The later COMPLETED `ERRATUM_MANIFEST.json` explicitly supersedes the original final package and binds the current six `corrected_reports/` files: {ref(E / 'ERRATUM_MANIFEST.json')}. Each of the six current file hashes was independently matched to that manifest during this archive preparation. {ref(E / 'ERRATUM.json')} records a metadata-only correction, preserved statistics bytes and preserved original reports/package/ZIP. This is a certified publication succession, not a conflicting replacement of historical SHA values.

The root publication receipt {ref(E / 'root_publication/PUBLICATION_RECEIPT.json')} binds previous root `c7b539bef23e3f43e1d663bc9240ab80cd325d2f1f7dd501e0b22cd18e3b8a3d` to current root `2a522ae64713ffc6e3cbe1389a7faac15d267dd123675590f5f813d50cf33368`, with earlier `f50fa7c8e6abd916124d423ad2b5950df2a7c631d02403eaf8e1cc5736f06ee8` preserved in the prior archive. The root retains a Draft title and the corrected reports retain a legacy requirement for a final DELIVERY_MANIFEST. The new final evidence archive therefore provides a separate formal index and manifest binding the exact copied corrected reports; historical files retain their original bytes and titles.

## Controlled model runtime

- Environment ID: `{environment['model_environment_id']}`.
- Actual model Python executable: `{environment['python_executable']}`; bound executable SHA256 `{environment['python_executable_sha256']}`.
- Actual interpreter: `{native['python']}`.
- Base interpreter/stdlib: `{environment['base_prefix']}`.
- Model site-packages: `{environment['site_packages_root']}`.
- Platform recorded in the experiment manifest: `{environment['platform']}`; `{environment['hardware']['processor']}`.
- Startup: isolated `-I -S -B`, explicitly add only the controlled new site-packages, `include-system-site-packages=false`; present `.pth` files inventoried but not executed.
- Saved actual CUDA compatibility result: Torch `{native['cuda']['torch_version']}`, compiled CUDA `{native['cuda']['torch_cuda_version']}`, `{native['cuda']['device_count']}` device, NVIDIA GeForce RTX 3060 Laptop GPU (compute capability 8.6, 6143 MB recorded by Torch).
- NumPy build evidence records OpenBLAS `0.3.31.188.0`; the saved Stage-B parity test checked 772 NumPy/native files with no mismatches before the model experiment.

These exact identities are bound by {ref(RESULT / 'provenance_manifest.json')}, {ref(ENV / 'MODEL_RUNTIME_SPEC.json')}, {ref(ENV / 'MODEL_ENVIRONMENT_RECOVERY_RECEIPT.json')} and the saved actual native compatibility receipt {ref(ENV / 'NATIVE_COMPATIBILITY_TEST_RECEIPT_ATTEMPT002.json')}. They are historical records of the controlled run; no claim is made that a new environment import was repeated during archive assembly.

## Exact saved dependency versions

| Distribution | Version |
|---|---|
{versions}

In particular pandas **2.3.3**, River **0.23.0**, psutil **7.2.2**, NumPy **2.4.6**, Torch **2.5.1+cu121**, scipy **1.17.1** and scikit-learn **1.9.0** were fixed before replication model outcomes. The complete distribution list is preserved in {ref(ENV / 'requirements_runtime_exact_freeze.txt')}.

## Dependency source and known limits

The saved official wheel metadata includes exact wheel filenames, URLs and archive digests. Wheel installation was offline, hash-enforced and dependency-resolved, with actual installation/pip-check receipts. Evidence: {ref(ENV / 'OFFICIAL_WHEELHOUSE_VERIFIED_V1.json')}, {ref(ENV / 'requirements_replication_env_v1.lock.txt')} and {ref(ENV / 'PIP_INSTALL_RECEIPT.json')}.

Torch/torchaudio/torchvision came from byte-for-byte copies of precisely frozen locally installed distributions, bound native files and populated RECORD digest/size fields: {ref(ENV / 'FROZEN_NATIVE_PACKAGE_COPY_RECEIPT.json')}. Their original archive download provenance remains **NOT_VERIFIED**; exact local installed-byte provenance is not substituted for an unavailable original archive digest. Python 3.11.15 uses the saved Anaconda base runtime/stdlib, with the independent venv isolating third-party site-packages. Pip 24.0 and setuptools 79.0.1 are separately recorded packaging tools. The saved model environment descriptor, imports, native maps and evidence file inventories provide precise source paths rather than inferring versions from a current unrelated interpreter.

The authorized compatibility change is pandas 3.0.5 → 2.3.3, plus fixed River 0.23.0, psutil 7.2.2 and pandas2.x's pytz 2025.2 dependency. Other frozen scientific dependency selections are retained as recorded. Historical complete runtime equivalence, GPU-driver binary history and fully identical numerical behavior remain **NOT_VERIFIED**. Windows/GPU driver or package-version gaps are not repaired retrospectively by marking them successful.

The installation inventory covers 23,716 non-bytecode files. The final experiment's science-runtime binding has 13,192 files checked by the v4 full audit. These are distinct scopes, not inconsistent counts. This prose task reads their saved inventories/certificates without repeating either full file traversal and hash pass.

## Frozen scientific source and stage chronology

The frozen protocol retains 20 centers 33000–33019, seeds 7311/7312/7313, scenarios C0/C1/C3/C4, methods B0/B1/B2/B8/P7.7, 24 stages, A1 and scaler, zero gate boundary, deployment limits, bank, candidate seed formula and 50 updates per candidate. The threshold, service unit, cost ratio and complete parameters are preserved verbatim in {ref(R / 'configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json')}; bank/source training manifests and frozen source are listed in `SOURCE_EVIDENCE_INDEX.json`. Binary model files are indexed with their previously verified manifest hashes and are not re-copied by this prose task.

The fixed F1 digest is `{manifest['input_bundle_digest']}` and replication manifest digest is `{manifest['manifest_digest']}`. The original provenance manifest was frozen before Stage C, so its `initial_state_verified=false` and `PENDING_STAGE_C` fields remain historical pre-execution statements. The later {ref(RESULT / 'initial_state_manifest.json')} and {ref(RESULT / 'full_experiment_integrity_gate.json')} supply the completed initial-reference and full paired-run evidence. No historical pending field is rewritten into a later success. The prior v4 audit {ref(V4 / 'FINAL_READONLY_ACCEPTANCE_004.json')} verified 2535 protected original files, all 1200 trajectories, all 240 paired groups and exact saved delivery/statistics bytes.

## Actual execution lineage, interruptions and metadata correction

The saved run combines 5 minimal trajectories, 118 retained A_FULL_0001 trajectories, 208 retained A_FULL_0002 trajectories, 1 real bridge-smoke trajectory and 868 A_DYNAMIC_0002 trajectories: 1200 total. Dynamic FULL retained 332 valid prior trajectories and completed 868 using a resource policy capped at three workers. Worker allocation depended on resource conditions, not loss values.

A_FULL_0001 disappeared without a saved terminal record. Its exit cause/code remain **NOT_VERIFIED**, and the observer's timestamp is an observation cutoff, not an invented actor finish. Evidence: {ref(RESULT / 'execution/full/A_FULL_0001/failure.json')}. A_FULL_0002 was intentionally interrupted for authorized dynamic takeover; its native termination evidence remains an interruption: {ref(B / 'replication_dynamic_takeover_v1/activation001/quiescence/actual_termination_evidence.json')}.

The bridge smoke actually launched DW0001 and DW0002. DW0001 alone owned and completed the one prespecified B1 trajectory. DW0002 received no TASK and retired with zero assigned trajectories. Both saved owning-backend exit receipts are zero; a late boundary STOP is not proof that DW0001 consumed that STOP. Evidence: {ref(E / 'SMOKE_PROCESS_COUNT_EVIDENCE.json')} and {ref(B / 'replication_dynamic_takeover_v1/activation001/real_model_bridge_smoke_certificate.json')}. Dynamic full coordinator actual exit zero is separately bound by {ref(B / 'replication_dynamic_takeover_v1/activation001/full_coordinator_exit.json')}. No universal bitwise scheduling-invariance claim follows.

The earlier metadata erratum and its supervisor failed with actual exit 1; their six failure files remain preserved. Metadata producer PID 10108 subsequently published the legally certified corrected artifacts, but its exit observer itself failed with actual 1 after waiting, before persisting the producer's exit receipt. Therefore PID 10108's actual exit remains **NOT_OBSERVED**: {ref(B / 'replication_dynamic_delivery_erratum_recovery_v2/ROOT_EXIT_OBSERVER_FAILURE_004.json')}. The new read-only finalizer PID 30796 has its own actual/native exit 0: {ref(POST / 'POSTPUBLICATION_PROCESS_EXIT_001.json')}; final auditor PID 12964 has its own actual exit 0: {ref(V4 / 'FINAL_READONLY_ACCEPTANCE_ACTUAL_EXIT_004.json')}. Acceptance covers current scientific artifacts and their independently finalized delivery, with `history_all_process_exits_verified=false`; it does not retroactively certify every process exit.

This is an integrity-correction replication using already observed canonical input. It is not a fresh unseen held-out study and does not automatically freeze the paper. Evidence archive integrity and manuscript scientific readiness remain separate decisions.
"""

write_new("SCIENTIFIC_CLAIM_BOUNDARY.md", claim)
write_new("SOURCE_ENVIRONMENT_PROVENANCE.md", provenance)
index = {"schema": "paper3-final-evidence-source-index-v1", "repository": str(R),
         "scope": "Selected textual source/protocol/environment/receipt evidence for archive; prior full v4 verification reused",
         "models_or_statistics_executed": False, "raw_or_full_environment_rescanned": False,
         "current_corrected_reports_checked_against_erratum_manifest": report_names,
         "evidence_files": entries, "binary_reference_only": binary_index,
         "prior_full_acceptance": str(V4 / "FINAL_READONLY_ACCEPTANCE_004.json"),
         "historical_environment_equivalence": "NOT_VERIFIED",
         "history_all_process_exits_verified": False,
         "manifest_relation": "Original COMPLETED DELIVERY_MANIFEST binds original reports; later COMPLETED ERRATUM_MANIFEST legally supersedes it and binds corrected report bytes",
         "manuscript_automatically_frozen": False}
write_new("SOURCE_EVIDENCE_INDEX.json", json.dumps(index, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": "DRAFT_ARTIFACTS_READY_FOR_ROOT_ARCHIVE", "files": {n: sha(OUT / n) for n in ["SCIENTIFIC_CLAIM_BOUNDARY.md", "SOURCE_ENVIRONMENT_PROVENANCE.md", "SOURCE_EVIDENCE_INDEX.json"]},
                  "selected_evidence_count": len(entries), "binary_references": len(binary_index)}, indent=2))
