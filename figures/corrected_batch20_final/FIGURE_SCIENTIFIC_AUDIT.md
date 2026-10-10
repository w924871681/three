# Paper 3 corrected batch20 figure scientific audit

Status: **PASS — numerical, source, scientific-claim, rendered-layout and file checks complete**. Fig2 and Fig3 are recommended for the main text. The final package manifest binds the precise release files; the independent ZIP receipt records post-packaging verification.

## Scope and source boundary

The figure data use only the verified integrity-correction replication in `D:/dt-talk/DT_LIFECYCLE_ESCALATION/results/p7_7_integrity_replication_batch20_env_v3/statistics_batch20_env_v3/`, bound to `D:/dt-talk/DT_LIFECYCLE_ESCALATION/handoffs/PAPER3_FINAL_VERIFIED_EVIDENCE/`. The formal archive's handoff, certificate, independent arithmetic verification, corrected final statistics report, delivery/package manifests and original statistics manifest/receipt supply the evidence chain.

`DATA_AUDIT.json` reports PASS for 102 selected metadata, byte-equality, summary-matrix and arithmetic checks, with zero failed checks. It verifies archived/live CSV byte identity and saved means/intervals, including genuine center pairs and integer search/action totals. This figure audit reuses completed raw/environment verification and performs no new model experiment, training, Bootstrap generation or all-environment rescan. No value comes from `original_mixed_inventory` or the old `results/p7_7` lifecycle results.

The scope remains previously observed canonical F1 batch20 inputs, not an independently unseen held-out evaluation. Historical environment equivalence remains NOT_VERIFIED; these figures do not resolve that limitation or freeze the manuscript.

## Fig. 2: numerical and inferential checks

The observed paired point estimates and saved intervals are read from `final_paired_contrasts.csv`, not inferred from the average Bootstrap replicate. The selected CSV is SHA256 `dccfb5249ac7c41ea7337e1fcd2f1f1dd4d00def630eb6b0eaa84662363c8da3`. Genuine center means are read from `final_metrics_by_center.csv`, SHA256 `49408ac23d337e879e124cfafbd45cc1fbb7947f4f509112830ffe325b13dc78`.

| Baseline | Observed Proposed − baseline | Saved 95% CI |
|---|---:|---|
| B0 | −0.0036641548764590783 | [−0.004573827822422219, −0.0028134015487948244] |
| B1 | −0.0004013360535383174 | [−0.0005435194434220294, −0.00027324824378676267] |
| B2 | −0.0019432976134592331 | [−0.0022800258030189167, −0.001616486006572207] |
| B8 | +0.000028016915328205657 | [−0.00000018594825329880642, +0.00008423669423791578] |

The protocol is 20 independent centers, 4,000 jointly paired center resamples, seed 2904, percentile 95% intervals from the saved shared index matrix. The four reported intervals are marginal; they do not assert simultaneous family-wise coverage. B0/B1/B2 intervals exclude zero on the lower-service-loss side. B8 crosses zero: superiority, equivalence and noninferiority are unsupported. No multiplicity correction, margin, alternative resampling procedure or new hypothesis test is introduced for drawing.

Panel (a) retains a complete common linear forest scale and a zero reference. A separate explicitly labeled B8 linear zoom includes zero and both interval endpoints; there is no broken main axis. Numeric endpoint annotation is especially important because the lower B8 endpoint is only slightly below zero. The same saved estimate and interval are rendered in the main forest and zoom.

Panel (b) shows all center IDs 33000–33019 in their original ID order. Differences are calculated only by subtracting the saved B8 center mean from the matching saved Proposed mean. There are 18 exact zeros, one positive observation (33000: +0.0005615779615861052) and one negative observation (33018: −0.0000012396550219920428). No center is removed, spread by invented jitter values, replaced by simulated values, or given a fabricated within-center confidence interval. Points are not connected: centers are independent evaluation units, not a temporal sequence. Observed equality does not imply equivalence, and concentration of the aggregate difference in very few centers must remain visible.

## Fig. 3: numerical and semantic checks

Values are taken from saved method/trajectory summaries and checked by integer aggregation of all 240 trajectories and 5,760 stage decisions per method. `final_execution_cost_by_method.csv` SHA256 is `70226a06ae6aaeb30f0de69aad7bf7aa1f38048eec7b77814344dac7b399d404`; `final_execution_cost_by_trajectory.csv` SHA256 is `067f6d991356bba5795bff28baa34f43a9cb03915386ca7ff2b8de6d1206f62f`.

| Quantity | B8 | Proposed |
|---|---:|---:|
| Admitted stages / all stages | 5,760 / 5,760 | 1,918 / 5,760 |
| Search admission rate | 100% | 33.298611111111114% |
| Evaluated feasible candidates | 53,280 | 17,428 |
| Candidate-search optimizer updates | 2,664,000 | 871,400 |
| Committed RI count | 105 | 104 |
| RI / all stages | 1.822916666666667% | 1.8055555555555554% |

Each candidate receives 50 updates; the candidate totals reproduce update totals exactly. This is not a single 50-update global budget. The search-admission rate is the frequency with which the alternative-model search gate is open, not the frequency of identity transition. The committed RI count is an action count, not the number of search candidates.

All three panels start at zero. Rates and exact observed totals are displayed without newly calculated error bars: the figure describes the complete saved evaluation matrix and does not claim population uncertainty for totals. Blue versus orange plus a hatch distinguishes methods in color and grayscale. Raw action penalties, attributed cached-call decision timers, standalone timing estimates and end-to-end elapsed cost are separate constructs. Fewer candidate optimizer updates alone do not demonstrate an equal-sized reduction in end-to-end time, energy or hardware cost.

## Optional Fig. 4 and table overlap

Omit Fig. 4. All 400 method × scenario × center means are available, so data insufficiency is not the reason. The existing four-scenario `tab:scenario` already presents the two-method service-loss comparison alongside gate-open and RI summaries. Avoiding that duplicate display is independent of favorable/unfavorable outcomes or significance. Preserve all C0, C1, C3 and C4 rows when the table is later updated under a separate manuscript authorization.

| Current LaTeX table | Recommendation for later authorized revision |
|---|---|
| `tab:methods`, line 173 | Keep the five-method behavior definitions; these are complementary to numerical plots. |
| `tab:main`, line 200 | Retain a compact table of five absolute service-loss means. Remove or move the duplicated paired contrast/CI columns to supplementary material because Fig. 2 supplies those estimates plus center heterogeneity. |
| `tab:actions`, line 223 | Retain maintenance, retain and action-cost context for all methods, or place the full table in supplementary material. Reduce repeated B8/Proposed gate-open and RI columns if space is limited. Candidate updates cannot replace the action-cost column. |
| `tab:scenario`, line 244 | Keep a corrected four-scenario table; no optional Fig. 4 is needed. Equal observed scenario means must not be described as equivalence. |

## Manuscript compatibility and unresolved prose updates

The repository's only complete Paper 3 LaTeX source found is `D:/dt-talk/DT_LIFECYCLE_ESCALATION/PAPER3_ORIGINAL_WORKING_MANUSCRIPT_UNMODIFIED.tex`, a preserved reconstructed original with IEEEtran journal class. Section 5 starts at line 160, Section 6 at 194 and Section 7 at 262. It still contains old experiment values and cannot serve as the data source for these corrected figures.

| Original manuscript location | Evidence-aligned issue requiring a later authorized prose/table update |
|---|---|
| Lines 161–166 | “Final Held-Out Protocol” and executed-once claims describe the earlier experiment; current evidence is an integrity-correction replication on previously observed F1 inputs. |
| Lines 207–211 | All five means and contrasts are stale; old B8 interval is wholly positive, while the corrected interval crosses zero. |
| Line 216 | Old leave-one-center-out values and the consistently unfavorable B8 wording must be reviewed against corrected saved statistics. |
| Lines 219–234 | Proposed gate-open 33.14%, RI rates and action table are stale. Corrected admission is approximately 33.30%; committed RI totals are 105 versus 104. |
| Lines 240–254 | Scenario table entries remain legacy values; use corrected saved scenario summaries later. |
| Line 260 | Old diagnostic counts are stale; the verified archive records missed escalation 2,100/5,760, an ongoing limitation. |
| Line 266 | The statement that the B8 paired interval remains on the unfavorable side contradicts the corrected interval crossing zero. |

Metric names remain “mean lifecycle service loss” (service MSE), “search admission rate (gate-open rate),” “candidate-search optimizer updates” and “committed re-instantiation (RI) count.” No core method definition is modified. C1 theoretical recoverability, finite supervised reference labels and the learned online score remain different objects; negative score is a search-admission rule, not proof of global unrecoverability.

## Visual reference and final layout checks

The Paper 1 style reference `D:/dt-talk/figures/fig2.png` was actually viewed; its source `D:/dt-talk/figures/draw_fig2.py:30–49` uses a white background, DejaVu Sans, dark text `#222222`, restrained blue `#6F8FAF` and orange `#C99A5A`. Only this typographic/color language is relevant; icons, flow-chart panels and decorative elements are not transferred to numerical figures.

The available Paper 3 source has an inline `fig:framework` TikZ figure at lines 129–158 with white background, dark strokes and compact labels. No separately named or separately certified newer “confirmed Fig. 1” image asset was located. This limitation is recorded rather than claiming a visual comparison that did not occur. Existing Fig. 1 and all old plots remain unchanged.

Final layout is Fig. 2 at 7.16 × 4.5 inches and Fig. 3 at 7.16 × 2.8 inches, both `figure*` with `width=\textwidth`. Native minimum text is 8 pt; reducing these composites to a single IEEE column is not recommended.

## Completed final QA

- 102 independent data checks: PASS; 22 independent scientific, preview-layout and caption checks: PASS. The exact review hashes bind the script, caption and plotted data. Final `PLOT_DATA.json` is byte-identical to the reviewed preview data.
- Matplotlib text-bounds and adjacent-tick tests: no clipped labels, no detected tick collisions, no missing glyph warnings, minimum 8 pt. Root and independent reviewer inspected color/grayscale previews. Root additionally inspected both actual final PDFs rendered through Poppler; all labels, centers and panels are readable without overlap.
- PNGs: 600 dpi, Fig2 4296 × 2700 and Fig3 4296 × 1680 pixels. PNG's integer pixels-per-meter metadata round-trips to 599.9988 dpi; this is the standard representation of 600 dpi.
- PDFs: one page each, correct native dimensions, vector paths/text, zero raster image objects, embedded TrueType descendant fonts, no Type3 fonts. The skill checker's generic Type0 embedding warning is retained in the QA record and resolved by directly traversing each descendant FontDescriptor and embedded FontFile stream. This is a checker limitation, not an ignored font failure.
- Four graphics regenerated once from the portable pinned input bundle: all four SHA256 values exactly reproduce. No Bootstrap or experiment was rerun.
- All 46 original figures, plotting scripts and manuscript files in the before-inventory remain byte-identical. The six selected source CSV hashes still match their completed receipt and archive.
- Only final 600 dpi PNGs are distributed; low-resolution review renders remain in the task audit workspace. Files, source evidence, numeric data and audit records are bound by `FIGURE_MANIFEST.json`; its own hash and the ZIP hash use sidecars to avoid circular references.

See `audit/FINAL_FILE_QA.json`, `audit/FINAL_RENDER_REVIEW.json`, `audit/REPRODUCIBILITY_CHECK.json`, `audit/INDEPENDENT_FIGURE_REVIEW.json` and `LAYOUT_CHECK.json` for concrete verification records. Existing manuscript corrections remain a separate, unperformed task; this figure release does not declare any paper section submission-ready or frozen.
