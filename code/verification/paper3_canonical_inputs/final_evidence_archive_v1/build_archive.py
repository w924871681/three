"""Additive final evidence archive. Copies saved bytes; never runs scientific code."""
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION')
BASE = ROOT / 'verification/paper3_canonical_inputs'
WORK = BASE / 'final_evidence_archive_v1'
SV = WORK / 'statistics_verification'
CP = WORK / 'claim_provenance'
V4 = BASE / 'replication_dynamic_delivery_recovery_v4'
OLD = ROOT / 'handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001'
RESULT = ROOT / 'results/p7_7_integrity_replication_batch20_env_v3'
STATS = RESULT / 'statistics_batch20_env_v3'
OUT = ROOT / 'handoffs/PAPER3_FINAL_VERIFIED_EVIDENCE'
ZIP = OUT.with_suffix('.zip')
REPORTS = ['EXECUTION_SUMMARY.md', 'INPUT_PARITY_AUDIT.md', 'EXPERIMENT_INTEGRITY_AUDIT.md',
           'CORRECTED_FINAL_STATISTICS.md', 'ORIGINAL_VS_REPLICATION_COMPARISON.md', 'SCIENTIFIC_FREEZE_DECISION.md']
PIN = {
    V4 / 'FINAL_READONLY_ACCEPTANCE_004.json': 'c4229bcd5f46612c5bb062412f1f2f308ea8ef44cda8fca9a12c5143cf003e64',
    V4 / 'FINAL_READONLY_ACCEPTANCE_PROCESS_004.json': 'f3f3a8258d0a9345f9487e9f7860e2695d72fb85db6d46bb2c927c2e993d298c',
    OLD / 'ERRATUM_MANIFEST.json': '2ada566465c1fe4f2bf4b6db0da22d8404cd6a0bdf8c7870820bb27e4df88bd8',
    ROOT / 'PAPER3_FINAL_REPLICATION_HANDOFF.md': '2a522ae64713ffc6e3cbe1389a7faac15d267dd123675590f5f813d50cf33368',
    SV / 'STATISTICS_VERIFICATION.json': '2542cb56c5b361c07b2b4514d0ee167ef3ff760bc316e803f9949251a0da1069',
    SV / 'STATISTICS_VERIFICATION_EXECUTION_RECEIPT.json': '10b1a9841ad0fc75b78f9cade80135e3b5d15d47b85b2e5a76d4af4f82907fa6',
    CP / 'SOURCE_EVIDENCE_INDEX.json': '42a8afeb77c8a7e5e61fe7c35f0293c0f6b733ab007fe3e0cd930559a0af659b',
    STATS / 'statistics_manifest.json': 'a2cd080532db281ca60ae89ee9edf5e272552689f8be9220eaf7c7857b3f1468',
    STATS / 'statistics_execution_receipt.json': '82585cf06c15e2bebc2d37bea90ccb9b6f24aa78745c00f6fd3378a0a0742dec',
    RESULT / 'provenance_manifest.json': 'c9277ed25b9c4e6df0b2ecfffeeefa3fdaa087ba4f326de828513402d5d20076',
    RESULT / 'initial_state_manifest.json': '18b329d5468d85961e28f24a1f45df9b2191530a9b26244642dbf6d2304e19dc',
    RESULT / 'full_experiment_integrity_gate.json': 'a33555e7f6083229aff520fe6e0a8f6ad11b2ef468cda3f8929be4cbe9240a97',
}
cache = {}
files = {}
origins = {}
source_dest = {}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read(path, expected=None):
    path = Path(path).resolve(strict=True)
    assert path.is_relative_to(ROOT), path
    assert not path.is_symlink(), path
    if path not in cache:
        cache[path] = path.read_bytes()
    data = cache[path]
    for digest in (expected, PIN.get(path)):
        if digest is not None:
            assert sha(data) == digest, ('SOURCE_SHA_CONFLICT', str(path), digest, sha(data))
    return data

def load(path):
    return json.loads(read(path))

def safe(rel):
    p = PurePosixPath(rel)
    assert not p.is_absolute() and '..' not in p.parts and ':' not in rel and '\\' not in rel, rel
    return str(p)

def copy(path, dest, expected=None, role='saved evidence'):
    path = Path(path).resolve(strict=True)
    dest = safe(dest)
    assert '/raw/' not in str(path).replace('\\', '/').lower(), ('RAW_COPY_FORBIDDEN', path)
    data = read(path, expected)
    if dest in files:
        assert files[dest] == data, ('DESTINATION_CONFLICT', dest)
    files[dest] = data
    origins[dest] = {'source_path': str(path), 'sha256': sha(data), 'size_bytes': len(data), 'role': role}
    source_dest.setdefault(str(path), dest)
    return dest

def generated(rel, obj):
    rel = safe(rel)
    assert rel not in files, rel
    files[rel] = (obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')

def bindings(names):
    return {name: sha(files[name]) for name in sorted(names)}

def main():
    assert not OUT.exists() and not ZIP.exists() and not Path(str(ZIP) + '.sha256').exists(), 'NO_OVERWRITE'
    prior = load(V4 / 'FINAL_READONLY_ACCEPTANCE_004.json')
    prior_exit = load(V4 / 'FINAL_READONLY_ACCEPTANCE_PROCESS_004.json')
    assert prior['status'] == 'PASS' and prior_exit['actual_exit_code'] == 0
    assert prior_exit['result_sha256'] == PIN[V4 / 'FINAL_READONLY_ACCEPTANCE_004.json']
    numerical = load(SV / 'STATISTICS_VERIFICATION.json')
    numerical_exit = load(SV / 'STATISTICS_VERIFICATION_EXECUTION_RECEIPT.json')
    assert numerical['status'] == 'PASS' and numerical_exit['actual_verifier_exit_code'] == 0
    assert numerical['raw_csv_count'] == 1200 and numerical['raw_stage_count'] == 28800
    assert len(numerical['output_comparisons']) == 16
    assert all(v['status'] == 'PASS' for v in numerical['output_comparisons'].values())
    review = load(CP / 'INDEPENDENT_STATISTICS_STATIC_REVIEW.json')
    assert review['status'] == 'PASS'
    for name, digest in numerical_exit['outputs_sha256'].items():
        read(SV / name, digest)
    old_manifest = load(OLD / 'ERRATUM_MANIFEST.json')
    assert old_manifest['status'] == 'COMPLETED' and old_manifest['statistics_bytes_unchanged']
    for name in REPORTS:
        rel = 'corrected_reports/' + name
        copy(OLD / rel, rel, old_manifest['package_files_sha256'][rel], 'current authoritative corrected report, byte-identical')
    for name in ['FINAL_STATISTICS_VERIFICATION.md']:
        copy(SV / name, name, numerical_exit['outputs_sha256'][name], 'new independent arithmetic verification')
    for name in ['SCIENTIFIC_CLAIM_BOUNDARY.md', 'SOURCE_ENVIRONMENT_PROVENANCE.md']:
        copy(CP / name, name, role='new scientific review boundary / provenance')
    for directory, prefix in [(SV, 'verification/statistics'), (CP, 'verification/claim_provenance'), (V4, 'verification/prior_full_acceptance')]:
        for path in sorted(directory.glob('*')):
            if path.is_file():
                copy(path, prefix + '/' + path.name)
    copy(Path(__file__), 'verification/archive/build_archive.py', role='additive archive builder; no scientific code execution')
    for name in ['provenance_manifest.json', 'initial_state_manifest.json', 'full_experiment_integrity_gate.json']:
        copy(RESULT / name, 'manifests/' + name)
    initial = load(RESULT / 'initial_state_manifest.json')
    gate = load(RESULT / 'full_experiment_integrity_gate.json')
    assert initial['completed_cases'] == 60 and initial['expected_cases'] == 60
    assert gate['scientific_integrity_pass'] and gate['trajectories'] == 1200 and gate['paired_groups'] == 240
    stats_manifest = load(STATS / 'statistics_manifest.json')
    for name in ['statistics_manifest.json', 'statistics_execution_receipt.json']:
        copy(STATS / name, 'manifests/' + name)
    for name, digest in stats_manifest['outputs_sha256'].items():
        copy(STATS / safe(name), 'statistics/' + safe(name), digest, 'unchanged saved numerical output')
    copy(SV / 'RAW_CSV_INDEX.json', 'indexes/RAW_CSV_INDEX.json', numerical_exit['outputs_sha256']['RAW_CSV_INDEX.json'])
    copy(SV / 'STATISTICS_INPUT_INDEX.json', 'indexes/STATISTICS_INPUT_INDEX.json', numerical_exit['outputs_sha256']['STATISTICS_INPUT_INDEX.json'])
    raw_index = load(SV / 'RAW_CSV_INDEX.json')
    assert raw_index['count'] == 1200 and len({r['path'] for r in raw_index['files']}) == 1200
    copy(ROOT / 'PAPER3_FINAL_REPLICATION_HANDOFF.md', 'history/PAPER3_FINAL_REPLICATION_HANDOFF_H2_UNMODIFIED.md')
    expected_old = set(old_manifest['package_files_sha256']) | {'ERRATUM_MANIFEST.json', 'ERRATUM_MANIFEST.json.sha256'}
    actual_old = {p.relative_to(OLD).as_posix() for p in OLD.rglob('*') if p.is_file()}
    assert actual_old == expected_old, ('PRIOR_PACKAGE_INVENTORY_CONFLICT', actual_old ^ expected_old)
    for rel in sorted(expected_old):
        copy(OLD / rel, 'history/erratum_001/' + rel, old_manifest['package_files_sha256'].get(rel), 'complete unchanged prior erratum package and historical archives')
    assert read(OLD / 'ERRATUM_MANIFEST.json.sha256').decode().split()[0] == PIN[OLD / 'ERRATUM_MANIFEST.json']
    index = load(CP / 'SOURCE_EVIDENCE_INDEX.json')
    for entry in index['evidence_files']:
        path = Path(entry['source_path'])
        if str(path.resolve()) in source_dest:
            read(path, entry['sha256'])
        else:
            copy(path, 'evidence/' + entry['sha256'][:16] + '_' + path.name, entry['sha256'], entry['role'])
    now = datetime.now(timezone.utc).isoformat()
    map_name = 'indexes/ARCHIVE_SOURCE_MAP.json'
    generated(map_name, {'schema': 'paper3-final-archive-source-map-v1', 'copied_files': origins,
                        'source_path_to_first_archive_copy': source_dest,
                        'raw_csv_files_copied': 0, 'models_copied': 0,
                        'binary_reference_only': index['binary_reference_only']})
    generated('SOURCE_CHANGE_DESCRIPTION.md', '''# Source Change Description — Final Evidence Archive

This delivery adds an independent saved-number verifier, review boundary documents, a formal archive index, a certificate and package manifests. It does not edit frozen experiment code, methods, A1, thresholds, candidate budget, costs, seeds, model bank, centers, historical environment, raw results, existing numerical statistics, reports, root handoff or earlier ZIPs.

The completed v4 full audit is reused. It had already read and hashed 40,156 unique files, including 2535 protected originals and 13,192 bound runtime files. Repeating that environment/raw integrity pass was unnecessary. This archive adds only the previously absent independent arithmetic comparison of the existing 1200 CSVs and all sixteen saved outputs. Re-evaluating the saved statistical formulas and verifying the saved seeded bootstrap indices produces a verification report, not new model outcomes or a changed inference protocol. All comparisons passed; no unfavorable result was excluded.

The historical corrective executor loaded canonical F1 batch20 arrays and common initial references, isolated tasks and recorded provenance/RNG/causal evidence. Its scientific method remained frozen. Dynamic scheduling subsequently changed resource ownership; the metadata erratum corrected smoke counts to two started workers, one trajectory worker and one idle worker. These earlier changes and their actual failed attempts are preserved byte for byte in history/erratum_001, including the original SOURCE_CHANGE_DESCRIPTION and original final ZIP.

The existing root still says Draft. The new PAPER3_FINAL_VERIFIED_HANDOFF.md is the formal evidence index for this archive; it does not overwrite that root. The original DELIVERY_MANIFEST binds its original reports, ERRATUM_MANIFEST binds the six corrected reports, and this archive's new COMPLETED DELIVERY_MANIFEST binds the exact copied six corrected reports and the new formal documents. This is explicit publication succession, not rewriting historical hashes.

All copied source paths and hashes are in indexes/ARCHIVE_SOURCE_MAP.json. Verification implementations and receipts are included under verification/. Historical unknown process exits remain unknown, historical numerical environment equivalence remains NOT_VERIFIED, and no manuscript section is automatically frozen.
''')
    report_links = '\n'.join('- [' + n + '](corrected_reports/' + n + ')' for n in REPORTS)
    generated('PAPER3_FINAL_VERIFIED_HANDOFF.md', f'''# Paper 3 — Final Verified Scientific Evidence Handoff

**FINAL_EVIDENCE_ARCHIVED** — formal evidence archive for independent scientific manuscript review.

Paper: *Bounded Maintenance Recoverability for Selective Lifecycle Escalation of Digital-Twin Models*.
Repository: `{ROOT}`. Saved experiment: `{RESULT}`. Archive assembled UTC: {now}.

## What has actually been verified

The completed independent v4 audit (actual exit 0, 2026-10-10 19:46:58 Beijing time) is reused for all full source/model/input/environment/causal and delivery checks. It verified 1200 unique trajectories, 240 paired five-method groups, 60 certified initial references, 28,800 complete stage records, canonical F1 input, frozen scientific bindings and 2535 unchanged protected original files. Its result, execution receipt, implementation and source-preservation reviews are packaged under verification/prior_full_acceptance. No 13,192-file environment rescan was performed for this archive.

The added independent arithmetic verification read each corrective CSV once, checked its saved SHA and receipt, and reproduced all sixteen existing numerical outputs within the declared tolerances (maximum observed absolute difference 0). It took {numerical['elapsed_seconds']:.3f} seconds and read {numerical['evidence_bytes_read']:,} bytes. The shared 4000×20 bootstrap indices exactly match seed 2904. No new model experiment was run and no original result was overwritten.

## Start here

- [Final integrity certificate](FINAL_INTEGRITY_CERTIFICATE.json)
- [Independent statistics verification](FINAL_STATISTICS_VERIFICATION.md)
- [Scientific claim boundaries](SCIENTIFIC_CLAIM_BOUNDARY.md)
- [Exact environment and source provenance](SOURCE_ENVIRONMENT_PROVENANCE.md)
- [Archive-only source change description](SOURCE_CHANGE_DESCRIPTION.md)
- [COMPLETED delivery manifest](DELIVERY_MANIFEST.json)
- [Exact package file hashes](PACKAGE_MANIFEST.json)

## Authoritative corrected reports

These six are exact copies of the latest certified ERRATUM_001 corrected_reports, with their final hashes bound by this archive's DELIVERY_MANIFEST. Preserve their historical wording; the formal index here resolves their inherited Draft/manifest delivery instructions.

{report_links}

## Saved statistics and raw evidence

All sixteen saved outputs are in statistics/, including observed center/scenario/method means, contrasts, every saved bootstrap replicate and joint_center_resample_indices.npy. Their original manifests and execution receipt are in manifests/.

[Complete raw index](indexes/RAW_CSV_INDEX.json) lists all 1200 raw CSV absolute paths, hashes and corresponding receipt hashes. No raw CSV was copied. [Statistics input bindings](indexes/STATISTICS_INPUT_INDEX.json) and [archive source map](indexes/ARCHIVE_SOURCE_MAP.json) connect packaged evidence to actual original paths. Full input/source/config/environment/result manifests, failure records and earlier reports/ZIP are preserved in history/erratum_001 and evidence/; use the source map to locate any original path within this ZIP. Original raw/model/environment binaries remain external to this review package, as requested.

## Results that constrain the paper

P7.7 has lower mean service loss than B0/B1/B2 under the frozen marginal 95% bootstrap-interval procedure. P7.7 minus B8 is +0.000028016915328205657 with 95% CI [-0.00000018594825329880642, +0.00008423669423791578]. The interval crosses zero: superiority, equivalence and noninferiority are not established. The four intervals do not promise simultaneous family-wise coverage. Missed escalation is 2100/5760 under finite offline reference labels and remains a limitation. Search workload and attributed decision timers do not establish full end-to-end computational cost.

## Scope and retained historical uncertainty

This is an integrity-correction replication using previously observed canonical F1 batch20 inputs, not a newly unseen held-out experiment. Complete historical environment numerical equivalence remains NOT_VERIFIED. Bridge smoke started two workers; one performed the single trajectory and the other received no TASK. A_FULL_0001's unobserved exit cause remains unknown; A_FULL_0002's intentional cutover is not relabeled successful. Metadata producer PID 10108's exit remains NOT_OBSERVED after observer failure; independent finalizer PID 30796 and v4 auditor PID 12964 have their own actual exit-0 receipts. Universal bitwise invariance across worker schedules is not claimed.

Theoretical C1 recoverability, finite reference labels and learned online scores remain different objects; q<0 is search admission and 50 updates is per candidate. No Sections 3–4 or full-paper submission freeze is authorized. This package is ready for scientific review, not a declaration that the manuscript's scientific claims are already accepted.

## Preservation and integrity chain

Existing root SHA256 `{PIN[ROOT / 'PAPER3_FINAL_REPLICATION_HANDOFF.md']}` is preserved unchanged as history/PAPER3_FINAL_REPLICATION_HANDOFF_H2_UNMODIFIED.md. Earlier H1/F50 roots and all prior reports remain in history/erratum_001. The prior manifest-to-erratum chain is certified and has no detected SHA conflict.

PACKAGE_MANIFEST hashes every file except itself and its SHA sidecar. The sidecar hashes the manifest; the external ZIP sidecar hashes the complete ZIP. This avoids circular self-hashes. ZIP member inventory and hashes are verified after creation. An actual assembly/ZIP verification receipt is retained alongside the builder outside the sealed package.
''')
    formal = ['PAPER3_FINAL_VERIFIED_HANDOFF.md', 'FINAL_STATISTICS_VERIFICATION.md', 'SCIENTIFIC_CLAIM_BOUNDARY.md',
              'SOURCE_ENVIRONMENT_PROVENANCE.md', 'SOURCE_CHANGE_DESCRIPTION.md'] + ['corrected_reports/' + n for n in REPORTS]
    certificate = {
        'schema': 'paper3-final-verified-integrity-certificate-v1', 'status': 'PASS', 'created_utc': now,
        'scope': 'saved scientific evidence and independent numerical consistency; historical uncertainties retained',
        'repository': str(ROOT), 'results': str(RESULT), 'prior_complete_verification_reused': True,
        'prior_full_acceptance_sha256': PIN[V4 / 'FINAL_READONLY_ACCEPTANCE_004.json'],
        'prior_full_acceptance_actual_exit_code': 0, 'prior_observed_utc': prior['observed_utc'],
        'prior_checks': prior['checks'], 'initial_references': {'completed': 60, 'expected': 60, 'manifest': 'manifests/initial_state_manifest.json'},
        'statistics_independent_verification': {'status': 'PASS', 'actual_exit_code': 0, 'outputs': 16,
            'maximum_absolute_numeric_difference': numerical_exit['maximum_absolute_numeric_difference'],
            'bootstrap': numerical['bootstrap'], 'comparison_tolerance': numerical['comparison_tolerance']},
        'evidence_sha256': bindings([source_dest[str(V4 / 'FINAL_READONLY_ACCEPTANCE_004.json')],
            source_dest[str(V4 / 'FINAL_READONLY_ACCEPTANCE_PROCESS_004.json')],
            source_dest[str(SV / 'STATISTICS_VERIFICATION.json')], source_dest[str(SV / 'STATISTICS_VERIFICATION_EXECUTION_RECEIPT.json')],
            source_dest[str(CP / 'INDEPENDENT_STATISTICS_STATIC_REVIEW.json')],
            'manifests/initial_state_manifest.json', 'manifests/full_experiment_integrity_gate.json', 'manifests/provenance_manifest.json',
            'manifests/statistics_manifest.json', 'manifests/statistics_execution_receipt.json', 'indexes/RAW_CSV_INDEX.json']),
        'formal_documents_sha256': bindings(formal), 'frozen_manifest_digest': prior['manifest_digest'],
        'F1_input_bundle_digest': prior['input_bundle_digest'], 'protected_original_files': 2535,
        'historical_environment_numerical_equivalence': 'NOT_VERIFIED', 'history_all_process_exits_verified': False,
        'metadata_original_producer_exit': 'NOT_OBSERVED; ROOT_EXIT_OBSERVER_FAILED',
        'models_or_new_experiments_run_for_archive': False, 'original_files_modified': False,
        'new_unseen_heldout_claimed': False, 'manuscript_automatically_frozen': False,
        'package_integrity_binding': 'This certificate is bound by DELIVERY_MANIFEST and PACKAGE_MANIFEST; ZIP verification is external to avoid self-reference.'}
    generated('FINAL_INTEGRITY_CERTIFICATE.json', certificate)
    generated('DELIVERY_MANIFEST.json', {
        'schema': 'paper3-final-verified-evidence-delivery-v1', 'status': 'COMPLETED', 'created_utc': now,
        'formal_entry': 'PAPER3_FINAL_VERIFIED_HANDOFF.md', 'formal_reports_sha256': bindings(formal),
        'integrity_certificate_sha256': sha(files['FINAL_INTEGRITY_CERTIFICATE.json']),
        'statistics_outputs_sha256': bindings(['statistics/' + n for n in stats_manifest['outputs_sha256']]),
        'supersedes_for_review_navigation_only': str(OLD), 'prior_erratum_manifest_sha256': PIN[OLD / 'ERRATUM_MANIFEST.json'],
        'old_reports_root_results_and_zips_overwritten': False, 'historical_unknown_exits_preserved': True,
        'raw_index': 'indexes/RAW_CSV_INDEX.json', 'raw_csv_count': 1200, 'raw_csv_copied': 0,
        'paired_method_groups': 240, 'initial_references': 60,
        'claim_scope': 'integrity-correction replication; no manuscript freeze; no B8 superiority or equivalence claim'})
    generated('DELIVERY_MANIFEST.json.sha256', sha(files['DELIVERY_MANIFEST.json']) + '  DELIVERY_MANIFEST.json\n')
    generated('PACKAGE_MANIFEST.json', {
        'schema': 'paper3-final-verified-evidence-package-v1', 'status': 'COMPLETED', 'created_utc': now,
        'package_root': OUT.name, 'files_sha256': bindings(list(files)),
        'files_size_bytes': {n: len(files[n]) for n in sorted(files)},
        'self_and_sidecar_excluded': ['PACKAGE_MANIFEST.json', 'PACKAGE_MANIFEST.json.sha256'],
        'raw_csv_files_copied': 0, 'scientific_binaries_reference_only': True,
        'external_zip_sidecar': ZIP.name + '.sha256'})
    generated('PACKAGE_MANIFEST.json.sha256', sha(files['PACKAGE_MANIFEST.json']) + '  PACKAGE_MANIFEST.json\n')
    # Exclusive creation after every input, binding and scientific status has passed.
    OUT.mkdir(exist_ok=False)
    for rel, data in sorted(files.items()):
        target = OUT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as handle:
            handle.write(data)
    for rel, data in files.items():
        assert sha((OUT / rel).read_bytes()) == sha(data), ('PACKAGE_WRITE_MISMATCH', rel)
    assert {p.relative_to(OUT).as_posix() for p in OUT.rglob('*') if p.is_file()} == set(files)
    with zipfile.ZipFile(ZIP, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for rel in sorted(files):
            archive.write(OUT / rel, OUT.name + '/' + rel)
    with zipfile.ZipFile(ZIP, 'r') as archive:
        members = archive.namelist()
        assert len(members) == len(set(members)) == len(files)
        assert set(members) == {OUT.name + '/' + n for n in files}
        for rel, data in files.items():
            assert sha(archive.read(OUT.name + '/' + rel)) == sha(data), ('ZIP_MEMBER_MISMATCH', rel)
    zip_digest = sha(ZIP.read_bytes())
    with Path(str(ZIP) + '.sha256').open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(zip_digest + '  ' + ZIP.name + '\n')
    # Only source handles were opened rb; explicitly reconfirm authoritative root and all 16 saved outputs.
    unchanged = {str(p): sha(p.read_bytes()) for p in [ROOT / 'PAPER3_FINAL_REPLICATION_HANDOFF.md'] + [STATS / n for n in stats_manifest['outputs_sha256']]}
    assert unchanged[str(ROOT / 'PAPER3_FINAL_REPLICATION_HANDOFF.md')] == PIN[ROOT / 'PAPER3_FINAL_REPLICATION_HANDOFF.md']
    assert all(unchanged[str(STATS / n)] == h for n, h in stats_manifest['outputs_sha256'].items())
    receipt = {'schema': 'paper3-final-evidence-archive-assembly-receipt-v1', 'status': 'FINAL_EVIDENCE_ARCHIVED',
        'finished_utc': datetime.now(timezone.utc).isoformat(), 'archive': str(OUT), 'zip_path': str(ZIP),
        'zip_sha256': zip_digest, 'zip_bytes': ZIP.stat().st_size, 'files': len(files),
        'package_bytes': sum(map(len, files.values())), 'directory_inventory_and_all_sha256_verified': True,
        'zip_inventory_and_all_member_sha256_verified': True, 'raw_csv_copied': 0,
        'package_manifest_sha256': sha(files['PACKAGE_MANIFEST.json']), 'delivery_manifest_sha256': sha(files['DELIVERY_MANIFEST.json']),
        'certificate_sha256': sha(files['FINAL_INTEGRITY_CERTIFICATE.json']),
        'source_root_and_statistics_preserved': unchanged, 'models_or_original_statistics_runner_executed': False,
        'historical_unknown_exits_preserved': True}
    with (WORK / 'ARCHIVE_ASSEMBLY_RECEIPT.json').open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True)
        handle.write('\n')
    print(json.dumps(receipt, indent=2))

if __name__ == '__main__':
    main()
