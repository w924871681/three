# Paper 3 corrected batch20 figure data provenance

Status: **PASS**. The two figures use only the formally verified integrity-correction replication. No original mixed-input measurements, old lifecycle image, simulated center, interpolation, new experiment or recomputed Bootstrap supplies plot data.

## Authority and files actually read

- Repository: `D:/dt-talk/DT_LIFECYCLE_ESCALATION`.
- Corrective statistics: `D:/dt-talk/DT_LIFECYCLE_ESCALATION/results/p7_7_integrity_replication_batch20_env_v3/statistics_batch20_env_v3`.
- Formal source archive: `D:/dt-talk/DT_LIFECYCLE_ESCALATION/handoffs/PAPER3_FINAL_VERIFIED_EVIDENCE`.
- Original dataset gate: 1,200 trajectories, 240 paired method groups, 60 initial references, 24 stages; canonical F1 batch20. These previously completed raw/input/environment checks are reused, not rerun for drawing.
- Read the official archived `PAPER3_FINAL_VERIFIED_HANDOFF.md`, `FINAL_INTEGRITY_CERTIFICATE.json`, `FINAL_STATISTICS_VERIFICATION.md` and latest `corrected_reports/CORRECTED_FINAL_STATISTICS.md`. The selected documents are bundled under `source_evidence/`; the certificate is in `inputs/`.
- The latest corrected report originates from `handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001/corrected_reports/`. Its final archived SHA is `77d58be3329be332916967bc51e779f16c1b11b22542207e2c50055b717963fc`.

`inputs/PACKAGE_MANIFEST.json` (SHA `5a30e5519ed3fde36e78e7e31e6918849fb5fd2814f635aac0a8e80fa2624fde`) binds the completed delivery, certificate, statistics manifest, receipt and selected CSVs. `DELIVERY_MANIFEST.json` is COMPLETED; the integrity certificate is PASS; `statistics_execution_receipt.json` is COMPLETED with actual exit 0. The generator requires each CSV hash to agree in the package, delivery, statistics manifest and receipt, then checks the live corrective source when `--repo` is supplied. The archive manifests describe the original larger evidence archive; their inclusion here does not imply that its entire contents were copied. The present figure-package inventory is exclusively `FIGURE_MANIFEST.json`.

| Corrected CSV in inputs/ | Use and fields | Exact SHA256 |
|---|---|---|
| `final_paired_contrasts.csv` | Fig2(a): mean_difference, ci_low, ci_high; saved n_centers, bootstrap_resamples, bootstrap_seed, point_estimate_source. | `dccfb5249ac7c41ea7337e1fcd2f1f1dd4d00def630eb6b0eaa84662363c8da3` |
| `final_metrics_by_center.csv` | Fig2(b): method + center_id key; lifecycle_service_loss; exact paired P7.7 minus B8 subtraction for all 20 IDs. | `49408ac23d337e879e124cfafbd45cc1fbb7947f4f509112830ffe325b13dc78` |
| `final_metrics_by_method.csv` | Cross-check all five mean_lifecycle_service_loss values and Fig3 gate_open_rate / ri_rate. | `9f4fc9db6d633fc8a3472c26d5ecc74791792ee4738d313b8cbbd764973f989e` |
| `final_metrics_by_trajectory.csv` | Fig3: stages, gate_open_count, ri_count summed across all 240 trajectories per method; full 1200-row uniqueness checked. | `012bd7a292b571714178fe369418b7d7e693dc498b514eff6fc437c5e4ccc8bd` |
| `final_execution_cost_by_method.csv` | Fig3(b): ri_search_updates_charged_total_recorded and feasible_candidate_count_total_recorded. | `70226a06ae6aaeb30f0de69aad7bf7aa1f38048eec7b77814344dac7b399d404` |
| `final_execution_cost_by_trajectory.csv` | Independent check of Fig3(b): ri_search_updates_charged_stage_sum summed across all 240 trajectories per method. | `067f6d991356bba5795bff28baa34f43a9cb03915386ca7ff2b8de6d1206f62f` |

`audit/DATA_AUDIT.json` records 102 selected source-chain and arithmetic checks. `PLOT_DATA.json` contains the exact observed values supplied to Matplotlib. The generator independently checks center/method contrasts and trajectory-to-method integer totals each time. The six CSVs are copied byte-for-byte from the verified archive and match their actual corrective result paths. Only small saved summary tables are read; 1,200 raw trajectory CSVs and 13,000 environment files are not rescanned.

## Statistical level and definitions

For service loss, the hierarchy is 24-stage trajectory means, three seeds and four scenarios within each center, then the mean of 20 independent centers. Each Fig2(b) point subtracts the two genuine saved means for the same center. IDs 33000–33019 remain in original order, including 18 exact zeros. Neither a zero observed difference nor the B8 interval crossing zero proves equivalence.

Fig2(a) uses the saved observed mean differences, not Bootstrap replicate averages. It displays the existing marginal percentile 95% intervals from 4,000 jointly paired center resamples, seed 2904. Shared resampling indices and bootstrap outputs were verified in the formal statistical archive; this task does not generate new indices, intervals, margins or tests. B8's saved interval crosses zero. The original and zoomed B8 marks use identical numeric values on explicitly labeled linear scales.

Fig3 admission equals total `gate_open_count` / total `stages`: B8 5,760/5,760; Proposed 1,918/5,760. Candidate updates equal the saved searched-candidate work: 53,280 × 50 = 2,664,000 and 17,428 × 50 = 871,400. Committed RI counts sum `ri_count`: 105 and 104. The 50-update budget is per candidate. These descriptive totals receive no invented confidence intervals. Search admission, searched-candidate work, final RI, action penalties, attributed timers and end-to-end cost are distinct quantities.

## Legacy inventory and manuscript boundary

`audit/manuscript_inventory.json` records the pre-drawing inventory. `scripts/plot_paper3_figures.py` reads legacy `results/p7_7` for lifecycle plots; none of those pixels or measurements is reused. Older P7.6B estimator-validation figures answer another question and are also excluded. The only complete Paper3 LaTeX found was `PAPER3_ORIGINAL_WORKING_MANUSCRIPT_UNMODIFIED.tex`; Sections 5–7 and its four tables were read, and stale values are listed in `FIGURE_SCIENTIFIC_AUDIT.md`.

Paper1 `D:/dt-talk/figures/fig2.png` was visually inspected for typography/palette only. The available Paper3 inline TikZ framework source was inspected; no separately certified newer Fig1 image was located. This limits claims of exact visual matching, but does not affect figure data. All 46 pre-existing figure, plotting-script and manuscript files in the before-inventory remain byte-identical. No manuscript or Fig1 is updated.

## Reproduction and rendering environment

Actual Python 3.11.15, Matplotlib 3.11.1, NumPy 2.4.6 and Pillow 12.3.0; Matplotlib Agg backend, DejaVu Sans, PDF fonttype 42, white background. The existing controlled site-packages were read without installing packages or changing the experimental environment. The model environment's historical numerical equivalence remains NOT_VERIFIED; plotting makes no new equivalence assertion.

Font file: `D:\dt-talk\DT_LIFECYCLE_ESCALATION\verification\paper3_canonical_inputs\model_env_recovery_v1_20261009\P7_7_REPLICATION_MODEL_ENV_V1\Lib\site-packages\matplotlib\mpl-data\fonts\ttf\DejaVuSans.ttf`; SHA256 `3fdf69cabf06049ea70a00b5919340e2ce1e6d02b0cc3c4b44fb6801bd1e0d22`.

Portable plotting command from the extracted package in an environment with the recorded libraries:

```powershell
python -B generate_paper3_figures.py --output NEW_EMPTY_OUTPUT_DIRECTORY --final
```

The default `inputs/` bundle is beside the script. Optional `--repo D:\dt-talk\DT_LIFECYCLE_ESCALATION` additionally compares all six selected source CSVs. Without `--final`, only review previews are produced. Use a fresh output directory to preserve this release. The script writes only its selected output and Matplotlib cache, never source data or manuscripts. The build used isolated `-I -S -B` Python with the existing controlled site-packages explicitly on `sys.path` and `MPLCONFIGDIR` set to this task's new audit directory.

Native sizes: Fig2 7.16 × 4.5 inches; Fig3 7.16 × 2.8 inches. Both are double-column `figure*`, `width=\textwidth`, minimum 8 pt text. PNGs are 600 dpi (4296 × 2700 and 4296 × 1680); PDFs contain vector paths/text and no raster image objects. One plotting-only rerun from the bundled inputs reproduced all four PDF/PNG SHA256 values exactly in the recorded runtime. Byte identity across different Matplotlib/font versions is not asserted.

All source hashes, script, graphics, captions and audit files are bound in `FIGURE_MANIFEST.json`. Its own SHA256 is external to avoid self-reference. The ZIP is independently hashed with a sidecar; its actual member set and bytes are checked after creation.
