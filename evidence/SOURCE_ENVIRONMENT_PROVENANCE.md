# Source and Environment Provenance — Paper 3 Final Evidence Archive

All statements below come from saved local manifests, runtime receipts, frozen source and the current corrected reports. This archive preparation imported no scientific package and launched no model, generator, training or statistical execution. Selected evidence documents are checked against their stored SHA256 bindings; the already completed v4 full environment/raw audit is reused.

## Current report authority and legal publication chain

The preserved original COMPLETED `DELIVERY_MANIFEST.json` binds the original results reports: [DELIVERY_MANIFEST.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001/original_v1_final_package/reviewed_delivery/DELIVERY_MANIFEST.json>) (SHA256 `aa5dae819d88ef95614276ffe79b2633a186c099a41709f704b6702835ae996b`). The later COMPLETED `ERRATUM_MANIFEST.json` explicitly supersedes the original final package and binds the current six `corrected_reports/` files: [ERRATUM_MANIFEST.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001/ERRATUM_MANIFEST.json>) (SHA256 `2ada566465c1fe4f2bf4b6db0da22d8404cd6a0bdf8c7870820bb27e4df88bd8`). Each of the six current file hashes was independently matched to that manifest during this archive preparation. [ERRATUM.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001/ERRATUM.json>) (SHA256 `6af0a15166cd756fbd6b135a31caacfd6857ee9a8452ad080126fe7adcb9baf1`) records a metadata-only correction, preserved statistics bytes and preserved original reports/package/ZIP. This is a certified publication succession, not a conflicting replacement of historical SHA values.

The root publication receipt [PUBLICATION_RECEIPT.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001/root_publication/PUBLICATION_RECEIPT.json>) (SHA256 `cabd2f16e8fdf5827da840f72464e4aeb292bf05565a3f2e3c9c0162692ae19f`) binds previous root `c7b539bef23e3f43e1d663bc9240ab80cd325d2f1f7dd501e0b22cd18e3b8a3d` to current root `2a522ae64713ffc6e3cbe1389a7faac15d267dd123675590f5f813d50cf33368`, with earlier `f50fa7c8e6abd916124d423ad2b5950df2a7c631d02403eaf8e1cc5736f06ee8` preserved in the prior archive. The root retains a Draft title and the corrected reports retain a legacy requirement for a final DELIVERY_MANIFEST. The new final evidence archive therefore provides a separate formal index and manifest binding the exact copied corrected reports; historical files retain their original bytes and titles.

## Controlled model runtime

- Environment ID: `P7_7_REPLICATION_MODEL_ENV_V1`.
- Actual model Python executable: `D:\dt-talk\DT_LIFECYCLE_ESCALATION\verification\paper3_canonical_inputs\model_env_recovery_v1_20261009\P7_7_REPLICATION_MODEL_ENV_V1\Scripts\python.exe`; bound executable SHA256 `8e83e4f932e02ffcf93d6ce00ef19791d9e78f1ca37fa2da31c45e99061d4dcc`.
- Actual interpreter: `3.11.15 | packaged by Anaconda, Inc. | (main, Jun 11 2026, 15:12:53) [MSC v.1942 64 bit (AMD64)]`.
- Base interpreter/stdlib: `C:\Users\92487\anaconda3\envs\rcf-dti-py311`.
- Model site-packages: `D:\dt-talk\DT_LIFECYCLE_ESCALATION\verification\paper3_canonical_inputs\model_env_recovery_v1_20261009\P7_7_REPLICATION_MODEL_ENV_V1\Lib\site-packages`.
- Platform recorded in the experiment manifest: `Windows-10-10.0.26200-SP0`; `Intel64 Family 6 Model 154 Stepping 3, GenuineIntel`.
- Startup: isolated `-I -S -B`, explicitly add only the controlled new site-packages, `include-system-site-packages=false`; present `.pth` files inventoried but not executed.
- Saved actual CUDA compatibility result: Torch `2.5.1+cu121`, compiled CUDA `12.1`, `1` device, NVIDIA GeForce RTX 3060 Laptop GPU (compute capability 8.6, 6143 MB recorded by Torch).
- NumPy build evidence records OpenBLAS `0.3.31.188.0`; the saved Stage-B parity test checked 772 NumPy/native files with no mismatches before the model experiment.

These exact identities are bound by [provenance_manifest.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/results/p7_7_integrity_replication_batch20_env_v3/provenance_manifest.json>) (SHA256 `c9277ed25b9c4e6df0b2ecfffeeefa3fdaa087ba4f326de828513402d5d20076`), [MODEL_RUNTIME_SPEC.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/model_env_recovery_v1_20261009/MODEL_RUNTIME_SPEC.json>) (SHA256 `7e029514ff3d955f1c6046eb8c339580f6cef7f192f95df7456191c855e9b425`), [MODEL_ENVIRONMENT_RECOVERY_RECEIPT.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/model_env_recovery_v1_20261009/MODEL_ENVIRONMENT_RECOVERY_RECEIPT.json>) (SHA256 `5ee17ce2ce055e5ac83e6351baf8d02ea125efbeaa6934837eebef3896242188`) and the saved actual native compatibility receipt [NATIVE_COMPATIBILITY_TEST_RECEIPT_ATTEMPT002.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/model_env_recovery_v1_20261009/NATIVE_COMPATIBILITY_TEST_RECEIPT_ATTEMPT002.json>) (SHA256 `435d65b6f2cfafb80d91583cc7def7c602e5a6306099472537dd0e66dc5cf64f`). They are historical records of the controlled run; no claim is made that a new environment import was repeated during archive assembly.

## Exact saved dependency versions

| Distribution | Version |
|---|---|
| `colorama` | `0.4.6` |
| `contourpy` | `1.3.3` |
| `cycler` | `0.12.1` |
| `filelock` | `3.32.0` |
| `fonttools` | `4.63.0` |
| `fsspec` | `2026.6.0` |
| `iniconfig` | `2.3.0` |
| `jinja2` | `3.1.6` |
| `joblib` | `1.5.3` |
| `kiwisolver` | `1.5.0` |
| `markupsafe` | `3.0.3` |
| `matplotlib` | `3.11.1` |
| `mpmath` | `1.3.0` |
| `narwhals` | `2.24.0` |
| `networkx` | `3.6.1` |
| `numpy` | `2.4.6` |
| `packaging` | `26.0` |
| `pandas` | `2.3.3` |
| `pillow` | `12.3.0` |
| `pip` | `24.0` |
| `pluggy` | `1.6.0` |
| `psutil` | `7.2.2` |
| `pygments` | `2.20.0` |
| `pyparsing` | `3.3.2` |
| `pypdf` | `6.14.2` |
| `pytest` | `9.1.1` |
| `python-dateutil` | `2.9.0.post0` |
| `pytz` | `2025.2` |
| `river` | `0.23.0` |
| `scikit-learn` | `1.9.0` |
| `scipy` | `1.17.1` |
| `setuptools` | `79.0.1` |
| `six` | `1.17.0` |
| `sympy` | `1.13.1` |
| `threadpoolctl` | `3.6.0` |
| `torch` | `2.5.1+cu121` |
| `torchaudio` | `2.5.1+cu121` |
| `torchvision` | `0.20.1+cu121` |
| `typing-extensions` | `4.16.0` |
| `tzdata` | `2026.3` |

In particular pandas **2.3.3**, River **0.23.0**, psutil **7.2.2**, NumPy **2.4.6**, Torch **2.5.1+cu121**, scipy **1.17.1** and scikit-learn **1.9.0** were fixed before replication model outcomes. The complete distribution list is preserved in [requirements_runtime_exact_freeze.txt](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/model_env_recovery_v1_20261009/requirements_runtime_exact_freeze.txt>) (SHA256 `50093d293be09370dca4902f111b040dcd9ac2f586d513440d4182d897c8d97b`).

## Dependency source and known limits

The saved official wheel metadata includes exact wheel filenames, URLs and archive digests. Wheel installation was offline, hash-enforced and dependency-resolved, with actual installation/pip-check receipts. Evidence: [OFFICIAL_WHEELHOUSE_VERIFIED_V1.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/model_env_recovery_v1_20261009/OFFICIAL_WHEELHOUSE_VERIFIED_V1.json>) (SHA256 `08f84a2bc8576d75deeb746067632bce419457ae3c514332871e8a843bf7a8c0`), [requirements_replication_env_v1.lock.txt](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/model_env_recovery_v1_20261009/requirements_replication_env_v1.lock.txt>) (SHA256 `5bea8214ac5ebecca44d2241157ca628b33410fe2c7d5cfcb120987e01f78d58`) and [PIP_INSTALL_RECEIPT.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/model_env_recovery_v1_20261009/PIP_INSTALL_RECEIPT.json>) (SHA256 `bf7b3064470ae0d6842eec0ec98c857cae173c28822f80a95d2b1b8b4eca36f6`).

Torch/torchaudio/torchvision came from byte-for-byte copies of precisely frozen locally installed distributions, bound native files and populated RECORD digest/size fields: [FROZEN_NATIVE_PACKAGE_COPY_RECEIPT.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/model_env_recovery_v1_20261009/FROZEN_NATIVE_PACKAGE_COPY_RECEIPT.json>) (SHA256 `f3be0b3e13554c59bc79fa97003e5a514f1b3a952d86f0e9fabfbc79e45090b3`). Their original archive download provenance remains **NOT_VERIFIED**; exact local installed-byte provenance is not substituted for an unavailable original archive digest. Python 3.11.15 uses the saved Anaconda base runtime/stdlib, with the independent venv isolating third-party site-packages. Pip 24.0 and setuptools 79.0.1 are separately recorded packaging tools. The saved model environment descriptor, imports, native maps and evidence file inventories provide precise source paths rather than inferring versions from a current unrelated interpreter.

The authorized compatibility change is pandas 3.0.5 → 2.3.3, plus fixed River 0.23.0, psutil 7.2.2 and pandas2.x's pytz 2025.2 dependency. Other frozen scientific dependency selections are retained as recorded. Historical complete runtime equivalence, GPU-driver binary history and fully identical numerical behavior remain **NOT_VERIFIED**. Windows/GPU driver or package-version gaps are not repaired retrospectively by marking them successful.

The installation inventory covers 23,716 non-bytecode files. The final experiment's science-runtime binding has 13,192 files checked by the v4 full audit. These are distinct scopes, not inconsistent counts. This prose task reads their saved inventories/certificates without repeating either full file traversal and hash pass.

## Frozen scientific source and stage chronology

The frozen protocol retains 20 centers 33000–33019, seeds 7311/7312/7313, scenarios C0/C1/C3/C4, methods B0/B1/B2/B8/P7.7, 24 stages, A1 and scaler, zero gate boundary, deployment limits, bank, candidate seed formula and 50 updates per candidate. The threshold, service unit, cost ratio and complete parameters are preserved verbatim in [P7_7_FINAL_LIFECYCLE_PROTOCOL.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json>) (SHA256 `6339a9247b984b497d1543198b3a7b7c0cfdf9c7bcfd1c52b47b62e17d2fd0df`); bank/source training manifests and frozen source are listed in `SOURCE_EVIDENCE_INDEX.json`. Binary model files are indexed with their previously verified manifest hashes and are not re-copied by this prose task.

The fixed F1 digest is `ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228` and replication manifest digest is `7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea`. The original provenance manifest was frozen before Stage C, so its `initial_state_verified=false` and `PENDING_STAGE_C` fields remain historical pre-execution statements. The later [initial_state_manifest.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/results/p7_7_integrity_replication_batch20_env_v3/initial_state_manifest.json>) (SHA256 `18b329d5468d85961e28f24a1f45df9b2191530a9b26244642dbf6d2304e19dc`) and [full_experiment_integrity_gate.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/results/p7_7_integrity_replication_batch20_env_v3/full_experiment_integrity_gate.json>) (SHA256 `a33555e7f6083229aff520fe6e0a8f6ad11b2ef468cda3f8929be4cbe9240a97`) supply the completed initial-reference and full paired-run evidence. No historical pending field is rewritten into a later success. The prior v4 audit [FINAL_READONLY_ACCEPTANCE_004.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/replication_dynamic_delivery_recovery_v4/FINAL_READONLY_ACCEPTANCE_004.json>) (SHA256 `c4229bcd5f46612c5bb062412f1f2f308ea8ef44cda8fca9a12c5143cf003e64`) verified 2535 protected original files, all 1200 trajectories, all 240 paired groups and exact saved delivery/statistics bytes.

## Actual execution lineage, interruptions and metadata correction

The saved run combines 5 minimal trajectories, 118 retained A_FULL_0001 trajectories, 208 retained A_FULL_0002 trajectories, 1 real bridge-smoke trajectory and 868 A_DYNAMIC_0002 trajectories: 1200 total. Dynamic FULL retained 332 valid prior trajectories and completed 868 using a resource policy capped at three workers. Worker allocation depended on resource conditions, not loss values.

A_FULL_0001 disappeared without a saved terminal record. Its exit cause/code remain **NOT_VERIFIED**, and the observer's timestamp is an observation cutoff, not an invented actor finish. Evidence: [failure.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/results/p7_7_integrity_replication_batch20_env_v3/execution/full/A_FULL_0001/failure.json>) (SHA256 `18d8c23454f21ddf4823e1c93be502a59659bfeb7e44ab590bc733b00af95cab`). A_FULL_0002 was intentionally interrupted for authorized dynamic takeover; its native termination evidence remains an interruption: [actual_termination_evidence.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/replication_dynamic_takeover_v1/activation001/quiescence/actual_termination_evidence.json>) (SHA256 `0fad1092713a712a5a578c8c573f12a3147401455d650ab42692a3b58b4f2744`).

The bridge smoke actually launched DW0001 and DW0002. DW0001 alone owned and completed the one prespecified B1 trajectory. DW0002 received no TASK and retired with zero assigned trajectories. Both saved owning-backend exit receipts are zero; a late boundary STOP is not proof that DW0001 consumed that STOP. Evidence: [SMOKE_PROCESS_COUNT_EVIDENCE.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001/SMOKE_PROCESS_COUNT_EVIDENCE.json>) (SHA256 `3cd6289af4c46b26931494933f8c4a8f50700e760f5c029e6b2f2892440c6a99`) and [real_model_bridge_smoke_certificate.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/replication_dynamic_takeover_v1/activation001/real_model_bridge_smoke_certificate.json>) (SHA256 `9aecc5900629ff534b2a04bf77e589c7e9380fce651def3516003e11e09b4834`). Dynamic full coordinator actual exit zero is separately bound by [full_coordinator_exit.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/replication_dynamic_takeover_v1/activation001/full_coordinator_exit.json>) (SHA256 `ec5c0b6b2ac65f3c17384014eececb8e361fb8368b90943d76f511ae49b673fd`). No universal bitwise scheduling-invariance claim follows.

The earlier metadata erratum and its supervisor failed with actual exit 1; their six failure files remain preserved. Metadata producer PID 10108 subsequently published the legally certified corrected artifacts, but its exit observer itself failed with actual 1 after waiting, before persisting the producer's exit receipt. Therefore PID 10108's actual exit remains **NOT_OBSERVED**: [ROOT_EXIT_OBSERVER_FAILURE_004.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/replication_dynamic_delivery_erratum_recovery_v2/ROOT_EXIT_OBSERVER_FAILURE_004.json>) (SHA256 `92de2eec50b9be2200eb02296b64e45ff927452d6eb4911ec577e24ebfa4f5c7`). The new read-only finalizer PID 30796 has its own actual/native exit 0: [POSTPUBLICATION_PROCESS_EXIT_001.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/replication_metadata_postpublication_finalize_v1/POSTPUBLICATION_PROCESS_EXIT_001.json>) (SHA256 `8e584d5929534d0eb299fcad65490c31f3ca8ade4fe41a1efc83dc67f4a250d8`); final auditor PID 12964 has its own actual exit 0: [FINAL_READONLY_ACCEPTANCE_ACTUAL_EXIT_004.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/replication_dynamic_delivery_recovery_v4/FINAL_READONLY_ACCEPTANCE_ACTUAL_EXIT_004.json>) (SHA256 `54fbe12b4f12cd75e517f9cd8b1235dce442b890123a97a5c26a05e056228396`). Acceptance covers current scientific artifacts and their independently finalized delivery, with `history_all_process_exits_verified=false`; it does not retroactively certify every process exit.

This is an integrity-correction replication using already observed canonical input. It is not a fresh unseen held-out study and does not automatically freeze the paper. Evidence archive integrity and manuscript scientific readiness remain separate decisions.
