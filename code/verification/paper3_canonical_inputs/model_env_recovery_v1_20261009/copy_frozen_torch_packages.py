import base64, csv, datetime, hashlib, json, pathlib, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent
SOURCE_PREFIX = pathlib.Path(r'C:\Users\92487\anaconda3\envs\rcf-dti-py311').resolve()
SOURCE_SITE = SOURCE_PREFIX / 'Lib' / 'site-packages'
TARGET_PREFIX = ROOT / 'P7_7_REPLICATION_MODEL_ENV_V1'
TARGET_SITE = TARGET_PREFIX / 'Lib' / 'site-packages'
PACKAGES = ['torch-2.5.1+cu121.dist-info', 'torchaudio-2.5.1+cu121.dist-info', 'torchvision-0.20.1+cu121.dist-info']
def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()
resume_verified_existing = '--resume-verified-existing' in sys.argv
if resume_verified_existing and not (ROOT / 'COPY_ATTEMPT_01_FAILURE_RECORD.json').is_file():
    raise RuntimeError('Explicit first-failure record required for no-overwrite resume')
all_files, excluded = [], []
seen_destination = set()
for info_name in PACKAGES:
    record = SOURCE_SITE / info_name / 'RECORD'
    rows = list(csv.reader(record.read_text(encoding='utf-8').splitlines()))
    print(f'Verifying/copying {info_name}: {len(rows)} records', flush=True)
    for relative, expected_digest, expected_size in rows:
        source = (SOURCE_SITE / relative).resolve()
        if not source.is_relative_to(SOURCE_PREFIX):
            raise RuntimeError(f'Unsafe source RECORD path {relative}')
        destination = (TARGET_SITE / relative).resolve()
        if not destination.is_relative_to(TARGET_PREFIX):
            raise RuntimeError(f'Unsafe destination RECORD path {relative}')
        if '__pycache__' in source.parts or source.suffix == '.pyc':
            excluded.append({'package': info_name, 'record_path': relative, 'reason': 'post-install CPython bytecode; not source/native; no bytecode execution'})
            continue
        if not source.is_file() or source.is_symlink():
            raise RuntimeError(f'Unavailable/nonregular frozen source {source}')
        source_sha = sha(source)
        if expected_digest:
            algorithm, value = expected_digest.split('=', 1)
            if algorithm != 'sha256' or base64.urlsafe_b64encode(bytes.fromhex(source_sha)).decode().rstrip('=') != value:
                raise RuntimeError(f'Frozen RECORD hash mismatch {source}')
        if expected_size and int(expected_size) != source.stat().st_size:
            raise RuntimeError(f'Frozen RECORD size mismatch {source}')
        preexisting_action = None
        if destination.exists():
            if not resume_verified_existing and str(destination) not in seen_destination:
                raise RuntimeError(f'No-overwrite violation {destination}')
            if sha(destination) != source_sha:
                raise RuntimeError(f'No-overwrite resume/duplicate hash mismatch {destination}')
            preexisting_action = 'VERIFIED_IDENTICAL_EXISTING_BYTES_NO_WRITE'
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        seen_destination.add(str(destination))
        destination_sha = sha(destination)
        if destination_sha != source_sha:
            raise RuntimeError(f'Copy hash mismatch {destination}')
        all_files.append({'distribution': info_name, 'record_path': relative, 'source': str(source), 'destination': str(destination), 'size': source.stat().st_size, 'sha256': source_sha, 'source_RECORD_digest': expected_digest, 'native': source.suffix.lower() in {'.dll', '.pyd'}, 'console_launcher_original_bytes_not_invoked': source.suffix.lower() == '.exe', 'preexisting_action': preexisting_action})
    print(f'Copied {info_name}', flush=True)
native_base = []
for path in [SOURCE_PREFIX / 'python.exe', SOURCE_PREFIX / 'python311.dll', SOURCE_PREFIX / 'vcruntime140.dll', SOURCE_PREFIX / 'vcruntime140_1.dll']:
    if path.is_file():
        native_base.append({'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size})
for folder in [SOURCE_PREFIX / 'DLLs', SOURCE_PREFIX / 'Library' / 'bin']:
    if folder.is_dir():
        for path in sorted(folder.glob('*')):
            if path.is_file() and path.suffix.lower() in {'.pyd', '.dll'}:
                native_base.append({'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size})
receipt = {'copy_completed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source_prefix': str(SOURCE_PREFIX), 'target_prefix': str(TARGET_PREFIX), 'files': all_files, 'excluded_post_install_bytecode': excluded, 'interpreter_base_native_snapshot': native_base, 'source_archive_download_origin': 'NOT_VERIFIED; source is preexisting precise installed frozen Py311 distribution; METADATA/WHEEL/RECORD and file bytes bound; no claim of original archive identity', 'editable_or_pth_copied': False, 'copied_scripts_launchers_policy': 'Original bytes copied only for complete RECORD provenance, never invoked; controlled task entrypoint is new venv Python executable', 'total_files_copied': len(all_files)}
with (ROOT / 'FROZEN_NATIVE_PACKAGE_COPY_RECEIPT.json').open('x', encoding='utf-8') as handle:
    json.dump(receipt, handle, indent=2)
print(f'PASS copied {len(all_files)} frozen files; excluded {len(excluded)} bytecode records', flush=True)
