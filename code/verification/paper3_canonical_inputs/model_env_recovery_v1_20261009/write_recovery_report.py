import hashlib, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parent
def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
receipt = read('MODEL_ENVIRONMENT_RECOVERY_RECEIPT.json')
native = read('NATIVE_COMPATIBILITY_TEST_RECEIPT_ATTEMPT002.json')
copy = read('FROZEN_NATIVE_PACKAGE_COPY_RECEIPT.json')
wheelhouse = read('OFFICIAL_WHEELHOUSE_VERIFIED_V1.json')
inventory = read('MODEL_ENVIRONMENT_FILE_INVENTORY.json')
if receipt['environment_status'] != 'ENVIRONMENT_READY' or native['status'] != 'PASS':
    raise RuntimeError('PASS required')
rows = []
for name in ['torch', 'torchaudio', 'torchvision', 'numpy', 'scipy', 'scikit-learn', 'pandas', 'river', 'psutil', 'pytz']:
    rows.append(f'| {name} | `{native["exact_versions"][name]}` | ' + ('exact frozen installed distribution copied byte-for-byte with source/destination SHA and RECORD verification' if name in {'torch', 'torchaudio', 'torchvision'} else 'official PyPI metadata + non-yanked compatible wheel, archive SHA verified, offline hash-enforced install') + ' |')
wheel_rows = [f'| {item["name"]}=={item["version"]} | `{item["wheel_sha256"]}` | {item["wheel_url"]} |' for item in wheelhouse['results']]
tests = [f'| `{name}` | {value} |' for name, value in native['tests'].items()]
text = f'''# Paper 3 — Independent Model Environment Recovery and Compatibility

**ENVIRONMENT_READY**. Exact dependency selection was fixed before any replication model result. All installation resolver checks and the complete corrected compatibility attempt are genuinely PASS. This document certifies the dependency/native environment only; checkpoint loading, initialization, trajectories, group fairness and statistics are separate root-agent stages and were not executed by the environment-recovery agent.

Target repository: `D:\\dt-talk\\DT_LIFECYCLE_ESCALATION`.

## Independent runtime identity

- Environment name: `P7_7_REPLICATION_MODEL_ENV_V1`.
- Prefix: `{ROOT / 'P7_7_REPLICATION_MODEL_ENV_V1'}`.
- Python: `{ROOT / 'P7_7_REPLICATION_MODEL_ENV_V1' / 'Scripts' / 'python.exe'}`, CPython3.11.15.
- Base interpreter/stdlib: `C:\\Users\\92487\\anaconda3\\envs\\rcf-dti-py311`; the venv shares only the normal CPython base runtime/stdlib, whose precise native source snapshot is bound. It does not inherit or import the old site-packages.
- `pyvenv.cfg`: `include-system-site-packages=false`.
- Controlled model startup: `-I -S -B`, explicitly insert only the new prefix's site-packages. Startup `.pth` files are inventoried and not processed by controlled model startup. No editable project was installed.
- Runtime descriptor: `{ROOT / 'MODEL_RUNTIME_SPEC.json'}`, SHA256 `{receipt['runtime_spec_sha256']}`.
- Recovery receipt: `{ROOT / 'MODEL_ENVIRONMENT_RECOVERY_RECEIPT.json'}`, SHA256 `{sha(ROOT / 'MODEL_ENVIRONMENT_RECOVERY_RECEIPT.json')}`.
- New prefix file inventory: `{ROOT / 'MODEL_ENVIRONMENT_FILE_INVENTORY.json'}`, {inventory['file_count']} bound non-bytecode files; environment fingerprint `{receipt['environment_fingerprint_sha256']}`.

## Exact scientific dependency choices and differences

| Package | Exact independent runtime version | Provenance |
|---|---|---|
{chr(10).join(rows)}

There are 35 exact `==` pins in the original requirements: 34 remain exact matches and the sole authorized replacement is pandas3.0.5→2.3.3. River0.23.0, psutil7.2.2 and pandas2.x's required pytz2025.2 are separately pinned additions. All other requirements pins are preserved. Original `requirements_frozen.txt`, original Python environments and frozen algorithm/model files are not modified by these recovery scripts. The unrelated editable Git package in the historical requirements was deliberately not installed: project execution uses the target repository's frozen sources, and an editable outside repository is not an authorized dependency source.

River0.23.0's official requirement is `pandas>=2.2.3,<3.0.0`, `numpy>=1.23.0`, `scipy>=1.14.1,<2.0.0`; pandas2.3.3 is a fixed non-yanked stable release with an exact CPython3.11 Windows wheel and satisfies that interval. psutil7.2.2 is the non-yanked stable version returned by official metadata, with cp37-abi3 Windows wheel compatible with CPython3.11; the original code's `virtual_memory/cpu_count` APIs were actually tested. It is not claimed to be the historical psutil version. pytz2025.2 is the exact official fixed release needed to satisfy pandas2.x's timezone dependency. These decisions preceded all new model outcomes and were not selected by loss or significance.

The venv bootstrap installs pip24.0/setuptools79.0.1 from the CPython3.11 ensurepip bundle. These packaging tools differ from the preexisting environment and are separately listed by `requirements_runtime_exact_freeze.txt`; they are not model algorithms. No original package was uninstalled or upgraded.

Historical complete final runtime equivalence is **NOT_VERIFIED**. The independent environment is neither represented as the exact historical runtime nor as an unseen held-out evaluation. Approved pandas compatibility changes can affect parsing or numeric support; they do not authorize changing scientific methods, input values, thresholds or selection rules. The root execution must still certify frozen checkpoint loading, input/initial-state/deployment fairness and causal traces.

## Frozen native copying and precise evidence limits

`FROZEN_NATIVE_PACKAGE_COPY_RECEIPT.json` records {copy['total_files_copied']} source/destination RECORD rows, including repeated normalized Windows aliases, with byte equality and verification of every populated RECORD digest/size. Torch, torchaudio and torchvision package/source/native bytes are copied into the independent prefix, never borrowed from an external site-packages at runtime. {len(copy['excluded_post_install_bytecode'])} generated bytecode rows are excluded; original bytecode remains untouched and controlled execution uses `-B`.

The preexisting distributions' original archive download provenance is **NOT_VERIFIED**. Their precise locally frozen installed bytes, native DLLs, metadata and RECORD are fully bound instead. This does not fabricate an archive SHA. Exact copied console launchers remain provenance material and are not invoked: all controlled entry commands use the new venv Python executable. Python base DLLs and native support libraries are recorded; Windows/GPU driver differences remain a historical equivalence limitation.

## Complete actual verification

Pip installation used all 35 verified official wheels with `--require-hashes --no-index --no-cache-dir`, and kept the dependency resolver enabled. Installation exited0. Both real pip-check attempts exited0 with `No broken requirements found.` No declaration conflict was ignored and no `--no-deps` installation was used.

| Check | Actual final result |
|---|---|
{chr(10).join(tests)}

StageB NumPy identity: all {native['stage_b_numpy_file_parity']['bound_file_count']} bound source/native files match exactly; no mismatch, no input regenerated. Original StageB environment manifest SHA `{native['stage_b_numpy_file_parity']['source_manifest_sha256']}`. The exact same NumPy/OpenBLAS/native bytes are retained despite the new package installation prefix.

CUDA actual test: Torch `{native['cuda']['torch_version']}`, CUDA `{native['cuda']['torch_cuda_version']}`, {native['cuda']['device_count']} device, `{native['cuda']['devices'][0]}`. CPU and CUDA matrix tests passed. River ADWIN received only a 1024-sample synthetic zero→one stream and detected drift at stored indices {native['adwin']['drift_detection_indices']}; no project telemetry, estimator fit, model training or optimization ran here.

The resource test recorded {native['resource_api']['memory_total_bytes']} bytes RAM and {native['resource_api']['memory_available_bytes_at_test']} available during that process, plus {native['resource_api']['cpu_count']} CPUs. These are resource observations, not model outcomes. The root scheduler may lower worker count under the existing authorization without changing scientific calculations.

Final actual check receipt: `{ROOT / 'NATIVE_COMPATIBILITY_TEST_RECEIPT_ATTEMPT002.json'}`; subprocess execution receipt: `{ROOT / 'ENVIRONMENT_CHECKS_EXECUTION_RECEIPT_ATTEMPT002.json'}`. The first native attempt's eight scientific/package checks already passed but overall failed at a new diagnostic logger accessing unsupported `pmmap_grouped.size`; its overall FAIL receipt and logs remain unmodified. The corrected logger uses the actual namedtuple `_asdict()` API, and the entire suite was rerun, not merely relabeled.

## Ordinary recovery implementation events

1. The metadata downloader initially rejected fonttools because both a cp311 native and a pure Python wheel existed. The independent finalizer selected the exact original cp311 ABI; original failure manifest remains.
2. A new metadata reader initially used Windows default GBK on official UTF-8 JSON. Explicit UTF-8 corrected only the new recovery helper.
3. Frozen torchvision RECORD includes slash and backslash spellings of identical physical paths. The first no-overwrite copy stopped; the explicit recovery compares every existing destination SHA exactly with its frozen source and never writes existing files. `COPY_ATTEMPT_01_FAILURE_RECORD.json` preserves that event.
4. The diagnostic memory-map logger error was corrected only in new verification code; previous source snapshots are in `ordinary_impl_fix_history/` and previous receipt/logs remain intact. Exact pins and computations were unchanged.

No stub, deleted algorithm import, Python3.13 native extension, scientific version substitution, result-conditioned selection or integrity bypass was used.

## Source archives and offline recreation

`requirements_replication_env_v1.lock.txt` binds all new official archive installs. `OFFICIAL_WHEELHOUSE_VERIFIED_V1.json` binds official metadata URL/bytes, wheel URL/size/SHA and fixed versions. `requirements_runtime_exact_freeze.txt` contains the complete installed distribution inventory. Recreate a separate CPython3.11 venv without system site-packages, replay the exact RECORD-verified frozen Torch-package copy, then install the fixed offline wheelhouse with the saved hash lock and enabled resolver. Rerun both pip check and the complete final compatibility script before checkpoint or experimental execution. Never run the copied old console launchers and never edit a finalized environment while an experiment is bound to its fingerprint.

| Fixed archive | SHA256 | Official wheel URL |
|---|---|---|
{chr(10).join(wheel_rows)}

## Authorization and scope boundary

The researcher explicitly authorized creating this independent Python3.11 runtime, River0.23.0, compatible pandas2.x, evidence-based psutil selection and controlled ordinary recovery fixes. This recovery does not certify initial model state, five-method parity, 1200 trajectories or center-level bootstrap. No checkpoint or project algorithm was loaded by this recovery agent. The root agent may automatically proceed to those already authorized stages only after its separate frozen SHA and scientific fairness gates pass. Any scientific conflict still stops progression.
'''
with (ROOT / 'MODEL_ENVIRONMENT_RECOVERY_AND_COMPATIBILITY_REPORT.md').open('x', encoding='utf-8') as handle:
    handle.write(text)
print('Recovery report written')
