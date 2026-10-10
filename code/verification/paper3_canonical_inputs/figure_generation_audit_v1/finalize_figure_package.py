"""Package only this task's new figures and selected evidence; no experiment code."""
from pathlib import Path
import datetime
import hashlib
import json
import zipfile

ROOT = Path(r'D:\dt-talk\DT_LIFECYCLE_ESCALATION')
AUDIT = ROOT / 'verification/paper3_canonical_inputs/figure_generation_audit_v1'
OUT = ROOT / 'figures/paper3_corrected_batch20_final'
ARCHIVE = ROOT / 'handoffs/PAPER3_FINAL_VERIFIED_EVIDENCE'
STAT = ROOT / 'results/p7_7_integrity_replication_batch20_env_v3/statistics_batch20_env_v3'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))

def write_new(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(content)

def copy_new(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as handle:
        handle.write(source.read_bytes())
    assert digest(source) == digest(destination)

def write_json(path, obj):
    write_new(path, json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + '\n')

qa = load(AUDIT / 'FINAL_FILE_QA.json')
repro = load(AUDIT / 'REPRODUCIBILITY_CHECK.json')
review = load(AUDIT / 'INDEPENDENT_FIGURE_REVIEW.json')
data_audit = load(AUDIT / 'DATA_AUDIT.json')
assert all(o['status'] == 'PASS' for o in [qa, repro, review, data_audit])
for name, pin in repro['byte_identical_files_sha256'].items():
    assert digest(OUT / name) == pin
assert digest(OUT / 'PLOT_DATA.json') == digest(AUDIT / 'preview/PLOT_DATA.json')
for path, record in review['reviewed_files'].items():
    assert digest(Path(path)) == record['sha256']
before = load(AUDIT / 'EXISTING_FIGURES_AND_MANUSCRIPT_BEFORE.json')
assert all(digest(Path(p)) == pin for p, pin in before.items())
package = load(OUT / 'inputs/PACKAGE_MANIFEST.json')['files_sha256']

for name in ['PAPER3_FINAL_VERIFIED_HANDOFF.md', 'FINAL_STATISTICS_VERIFICATION.md',
             'SCIENTIFIC_CLAIM_BOUNDARY.md', 'corrected_reports/CORRECTED_FINAL_STATISTICS.md']:
    source = ARCHIVE / name
    assert digest(source) == package[name]
    copy_new(source, OUT / 'source_evidence' / name)

for name in ['DATA_AUDIT.json', 'DATA_PROFILE.json', 'manuscript_inventory.json',
             'INDEPENDENT_FIGURE_REVIEW.json', 'FINAL_FILE_QA.json',
             'REPRODUCIBILITY_CHECK.json', 'EXISTING_FIGURES_AND_MANUSCRIPT_BEFORE.json']:
    copy_new(AUDIT / name, OUT / 'audit' / name)
copy_new(AUDIT / 'FIGURE_CAPTIONS.md', OUT / 'FIGURE_CAPTIONS.md')

visual = {
    'schema': 'paper3-final-pdf-render-review-v1', 'status': 'PASS',
    'reviewer': 'root; actual view_image inspection of Poppler-rendered final PDFs',
    'render_dpi_for_qa_only': 160,
    'checks': ['All labels readable at native two-column width', 'No clipped text or overlaps',
               'All 20 center IDs and observations retained', 'B8 zoom labeled, full CI and zero retained',
               'Different powers of ten explicitly printed on each relevant axis',
               'Fig3 axes start at zero; exact totals visible; method hatch distinct',
               'No decorative or raster image objects in vector PDF'],
    'rendered_files_sha256': {name: digest(AUDIT / name) for name in ['pdf_render_Fig2.png', 'pdf_render_Fig3.png']},
    'font_warning_resolution': (
        'Skill checker warning retained in FINAL_FILE_QA: its generic check inspects only the top-level '
        'FontDescriptor and misses Type0 DescendantFonts. Direct pypdf traversal confirmed every '
        'descendant has an embedded FontFile2/FontFile3 stream; there are no Type3 fonts. '
        'Final PDFs rendered successfully in Poppler. No font substitution or source changes were needed.'),
    'low_resolution_qa_previews_in_distribution': False,
}
write_json(OUT / 'audit/FINAL_RENDER_REVIEW.json', visual)

roles = {
    'final_paired_contrasts.csv': 'Fig2(a): mean_difference, ci_low, ci_high; saved n_centers, bootstrap_resamples, bootstrap_seed, point_estimate_source.',
    'final_metrics_by_center.csv': 'Fig2(b): method + center_id key; lifecycle_service_loss; exact paired P7.7 minus B8 subtraction for all 20 IDs.',
    'final_metrics_by_method.csv': 'Cross-check all five mean_lifecycle_service_loss values and Fig3 gate_open_rate / ri_rate.',
    'final_metrics_by_trajectory.csv': 'Fig3: stages, gate_open_count, ri_count summed across all 240 trajectories per method; full 1200-row uniqueness checked.',
    'final_execution_cost_by_method.csv': 'Fig3(b): ri_search_updates_charged_total_recorded and feasible_candidate_count_total_recorded.',
    'final_execution_cost_by_trajectory.csv': 'Independent check of Fig3(b): ri_search_updates_charged_stage_sum summed across all 240 trajectories per method.',
}
rows = '\n'.join(f'| `{name}` | {role} | `{digest(OUT / "inputs" / name)}` |' for name, role in roles.items())
runtime = qa['runtime']
provenance = f'''# Paper 3 corrected batch20 figure data provenance

Status: **PASS**. The two figures use only the formally verified integrity-correction replication. No original mixed-input measurements, old lifecycle image, simulated center, interpolation, new experiment or recomputed Bootstrap supplies plot data.

## Authority and files actually read

- Repository: `{ROOT.as_posix()}`.
- Corrective statistics: `{STAT.as_posix()}`.
- Formal source archive: `{ARCHIVE.as_posix()}`.
- Original dataset gate: 1,200 trajectories, 240 paired method groups, 60 initial references, 24 stages; canonical F1 batch20. These previously completed raw/input/environment checks are reused, not rerun for drawing.
- Read the official archived `PAPER3_FINAL_VERIFIED_HANDOFF.md`, `FINAL_INTEGRITY_CERTIFICATE.json`, `FINAL_STATISTICS_VERIFICATION.md` and latest `corrected_reports/CORRECTED_FINAL_STATISTICS.md`. The selected documents are bundled under `source_evidence/`; the certificate is in `inputs/`.
- The latest corrected report originates from `handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001/corrected_reports/`. Its final archived SHA is `77d58be3329be332916967bc51e779f16c1b11b22542207e2c50055b717963fc`.

`inputs/PACKAGE_MANIFEST.json` (SHA `5a30e5519ed3fde36e78e7e31e6918849fb5fd2814f635aac0a8e80fa2624fde`) binds the completed delivery, certificate, statistics manifest, receipt and selected CSVs. `DELIVERY_MANIFEST.json` is COMPLETED; the integrity certificate is PASS; `statistics_execution_receipt.json` is COMPLETED with actual exit 0. The generator requires each CSV hash to agree in the package, delivery, statistics manifest and receipt, then checks the live corrective source when `--repo` is supplied. The archive manifests describe the original larger evidence archive; their inclusion here does not imply that its entire contents were copied. The present figure-package inventory is exclusively `FIGURE_MANIFEST.json`.

| Corrected CSV in inputs/ | Use and fields | Exact SHA256 |
|---|---|---|
{rows}

`audit/DATA_AUDIT.json` records 102 selected source-chain and arithmetic checks. `PLOT_DATA.json` contains the exact observed values supplied to Matplotlib. The generator independently checks center/method contrasts and trajectory-to-method integer totals each time. The six CSVs are copied byte-for-byte from the verified archive and match their actual corrective result paths. Only small saved summary tables are read; 1,200 raw trajectory CSVs and 13,000 environment files are not rescanned.

## Statistical level and definitions

For service loss, the hierarchy is 24-stage trajectory means, three seeds and four scenarios within each center, then the mean of 20 independent centers. Each Fig2(b) point subtracts the two genuine saved means for the same center. IDs 33000–33019 remain in original order, including 18 exact zeros. Neither a zero observed difference nor the B8 interval crossing zero proves equivalence.

Fig2(a) uses the saved observed mean differences, not Bootstrap replicate averages. It displays the existing marginal percentile 95% intervals from 4,000 jointly paired center resamples, seed 2904. Shared resampling indices and bootstrap outputs were verified in the formal statistical archive; this task does not generate new indices, intervals, margins or tests. B8's saved interval crosses zero. The original and zoomed B8 marks use identical numeric values on explicitly labeled linear scales.

Fig3 admission equals total `gate_open_count` / total `stages`: B8 5,760/5,760; Proposed 1,918/5,760. Candidate updates equal the saved searched-candidate work: 53,280 × 50 = 2,664,000 and 17,428 × 50 = 871,400. Committed RI counts sum `ri_count`: 105 and 104. The 50-update budget is per candidate. These descriptive totals receive no invented confidence intervals. Search admission, searched-candidate work, final RI, action penalties, attributed timers and end-to-end cost are distinct quantities.

## Legacy inventory and manuscript boundary

`audit/manuscript_inventory.json` records the pre-drawing inventory. `scripts/plot_paper3_figures.py` reads legacy `results/p7_7` for lifecycle plots; none of those pixels or measurements is reused. Older P7.6B estimator-validation figures answer another question and are also excluded. The only complete Paper3 LaTeX found was `PAPER3_ORIGINAL_WORKING_MANUSCRIPT_UNMODIFIED.tex`; Sections 5–7 and its four tables were read, and stale values are listed in `FIGURE_SCIENTIFIC_AUDIT.md`.

Paper1 `{(ROOT.parent / 'figures/fig2.png').as_posix()}` was visually inspected for typography/palette only. The available Paper3 inline TikZ framework source was inspected; no separately certified newer Fig1 image was located. This limits claims of exact visual matching, but does not affect figure data. All 46 pre-existing figure, plotting-script and manuscript files in the before-inventory remain byte-identical. No manuscript or Fig1 is updated.

## Reproduction and rendering environment

Actual Python {runtime['python']}, Matplotlib {runtime['matplotlib']}, NumPy {runtime['numpy']} and Pillow {runtime['pillow']}; Matplotlib Agg backend, DejaVu Sans, PDF fonttype 42, white background. The existing controlled site-packages were read without installing packages or changing the experimental environment. The model environment's historical numerical equivalence remains NOT_VERIFIED; plotting makes no new equivalence assertion.

Font file: `{qa['font']['path']}`; SHA256 `{qa['font']['sha256']}`.

Portable plotting command from the extracted package in an environment with the recorded libraries:

```powershell
python -B generate_paper3_figures.py --output NEW_EMPTY_OUTPUT_DIRECTORY --final
```

The default `inputs/` bundle is beside the script. Optional `--repo D:\\dt-talk\\DT_LIFECYCLE_ESCALATION` additionally compares all six selected source CSVs. Without `--final`, only review previews are produced. Use a fresh output directory to preserve this release. The script writes only its selected output and Matplotlib cache, never source data or manuscripts. The build used isolated `-I -S -B` Python with the existing controlled site-packages explicitly on `sys.path` and `MPLCONFIGDIR` set to this task's new audit directory.

Native sizes: Fig2 7.16 × 4.5 inches; Fig3 7.16 × 2.8 inches. Both are double-column `figure*`, `width=\\textwidth`, minimum 8 pt text. PNGs are 600 dpi (4296 × 2700 and 4296 × 1680); PDFs contain vector paths/text and no raster image objects. One plotting-only rerun from the bundled inputs reproduced all four PDF/PNG SHA256 values exactly in the recorded runtime. Byte identity across different Matplotlib/font versions is not asserted.

All source hashes, script, graphics, captions and audit files are bound in `FIGURE_MANIFEST.json`. Its own SHA256 is external to avoid self-reference. The ZIP is independently hashed with a sidecar; its actual member set and bytes are checked after creation.
'''
write_new(OUT / 'FIGURE_DATA_PROVENANCE.md', provenance)

draft = (AUDIT / 'FIGURE_SCIENTIFIC_AUDIT_DRAFT.md').read_text(encoding='utf-8')
draft = draft.replace('# Paper 3 corrected batch20 figure scientific audit — draft for final QA', '# Paper 3 corrected batch20 figure scientific audit')
start = draft.index('Draft status:')
end = draft.index('\n\n', start)
draft = draft[:start] + ('Status: **PASS — numerical, source, scientific-claim, rendered-layout and file checks complete**. '
    'Fig2 and Fig3 are recommended for the main text. The final package manifest binds the precise release files; '
    'the independent ZIP receipt records post-packaging verification.') + draft[end:]
start = draft.index('Final layout targets are')
draft = draft[:start] + '''Final layout is Fig. 2 at 7.16 × 4.5 inches and Fig. 3 at 7.16 × 2.8 inches, both `figure*` with `width=\\textwidth`. Native minimum text is 8 pt; reducing these composites to a single IEEE column is not recommended.

## Completed final QA

- 102 independent data checks: PASS; 22 independent scientific, preview-layout and caption checks: PASS. The exact review hashes bind the script, caption and plotted data. Final `PLOT_DATA.json` is byte-identical to the reviewed preview data.
- Matplotlib text-bounds and adjacent-tick tests: no clipped labels, no detected tick collisions, no missing glyph warnings, minimum 8 pt. Root and independent reviewer inspected color/grayscale previews. Root additionally inspected both actual final PDFs rendered through Poppler; all labels, centers and panels are readable without overlap.
- PNGs: 600 dpi, Fig2 4296 × 2700 and Fig3 4296 × 1680 pixels. PNG's integer pixels-per-meter metadata round-trips to 599.9988 dpi; this is the standard representation of 600 dpi.
- PDFs: one page each, correct native dimensions, vector paths/text, zero raster image objects, embedded TrueType descendant fonts, no Type3 fonts. The skill checker's generic Type0 embedding warning is retained in the QA record and resolved by directly traversing each descendant FontDescriptor and embedded FontFile stream. This is a checker limitation, not an ignored font failure.
- Four graphics regenerated once from the portable pinned input bundle: all four SHA256 values exactly reproduce. No Bootstrap or experiment was rerun.
- All 46 original figures, plotting scripts and manuscript files in the before-inventory remain byte-identical. The six selected source CSV hashes still match their completed receipt and archive.
- Only final 600 dpi PNGs are distributed; low-resolution review renders remain in the task audit workspace. Files, source evidence, numeric data and audit records are bound by `FIGURE_MANIFEST.json`; its own hash and the ZIP hash use sidecars to avoid circular references.

See `audit/FINAL_FILE_QA.json`, `audit/FINAL_RENDER_REVIEW.json`, `audit/REPRODUCIBILITY_CHECK.json`, `audit/INDEPENDENT_FIGURE_REVIEW.json` and `LAYOUT_CHECK.json` for concrete verification records. Existing manuscript corrections remain a separate, unperformed task; this figure release does not declare any paper section submission-ready or frozen.
'''
write_new(OUT / 'FIGURE_SCIENTIFIC_AUDIT.md', draft)

payload = {p.relative_to(OUT).as_posix(): digest(p) for p in sorted(OUT.rglob('*')) if p.is_file()}
manifest = {
    'schema': 'paper3-corrected-batch20-figure-package-v1', 'status': 'FIGURES_READY',
    'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'scope': 'Two new figures from formally verified corrective batch20 saved statistics only',
    'figures': {
        'Fig2_Paired_Service_Loss': {'recommended_for_main_text': True, 'data_check': 'PASS', 'layout_check': 'PASS', 'width_inches': 7.16, 'height_inches': 4.5, 'minimum_font_pt': 8, 'png_dpi': 600, 'pdf_vector': True},
        'Fig3_Selective_Search': {'recommended_for_main_text': True, 'data_check': 'PASS', 'layout_check': 'PASS', 'width_inches': 7.16, 'height_inches': 2.8, 'minimum_font_pt': 8, 'png_dpi': 600, 'pdf_vector': True}},
    'optional_fig4': {'generated': False, 'reason': 'Redundant with corrected four-scenario table; complete center data available; choice independent of direction/significance'},
    'sources': {'formal_archive': str(ARCHIVE), 'statistics_root': str(STAT), 'source_sha256': load(OUT / 'PLOT_DATA.json')['input_sha256']},
    'protocol': {'centers': 20, 'bootstrap_resamples': 4000, 'bootstrap_seed': 2904, 'intervals_recomputed': False, 'point_estimates': 'Original observed center-mean differences', 'B8_CI_crosses_zero': True},
    'actual_runtime': qa['runtime'], 'font': qa['font'],
    'reproducibility': {'all_four_graphics_byte_identical_on_one_rerender': True},
    'existing_protected_files_unchanged': len(before), 'manuscript_modified': False,
    'experiments_or_training_run': False, 'AI_images_or_seaborn_used': False, 'original_mixed_plot_data_used': False,
    'input_bundle_is_selected_subset_of_scientific_archive': True,
    'files_sha256': payload,
    'self_reference_policy': 'This manifest and its sidecar are outside files_sha256; the sidecar binds this manifest. External ZIP SHA sidecar and post-packaging receipt bind the exact complete ZIP.'
}
write_json(OUT / 'FIGURE_MANIFEST.json', manifest)
write_new(OUT / 'FIGURE_MANIFEST.json.sha256', digest(OUT / 'FIGURE_MANIFEST.json') + '  FIGURE_MANIFEST.json\n')

zip_path = OUT.with_suffix('.zip')
members = {p.relative_to(OUT).as_posix(): digest(p) for p in sorted(OUT.rglob('*')) if p.is_file()}
with zipfile.ZipFile(zip_path, mode='x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
    for name in members:
        bundle.write(OUT / name, arcname=OUT.name + '/' + name)
with zipfile.ZipFile(zip_path, mode='r') as bundle:
    assert bundle.testzip() is None
    assert set(bundle.namelist()) == {OUT.name + '/' + name for name in members}
    for name, pin in members.items():
        assert hashlib.sha256(bundle.read(OUT.name + '/' + name)).hexdigest() == pin
zip_hash = digest(zip_path)
write_new(Path(str(zip_path) + '.sha256'), zip_hash + '  ' + zip_path.name + '\n')
receipt = {'schema': 'paper3-figure-package-completion-v1', 'status': 'FIGURES_READY',
           'zip_path': str(zip_path), 'zip_sha256': zip_hash, 'zip_bytes': zip_path.stat().st_size,
           'zip_members': len(members), 'zip_all_members_crc_and_sha256_verified': True,
           'figure_manifest_sha256': digest(OUT / 'FIGURE_MANIFEST.json'),
           'payload_files': len(payload), 'source_and_preservation_checks': 'PASS'}
write_json(AUDIT / 'FIGURE_PACKAGE_COMPLETION_RECEIPT.json', receipt)
print(json.dumps(receipt, ensure_ascii=False, indent=2))
