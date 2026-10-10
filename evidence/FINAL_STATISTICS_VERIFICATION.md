# Final Statistics Verification

Status: **PASS**. Independent numerical verification of existing saved results; no model execution.

The prior v4 full acceptance is reused for scientific provenance, paired inputs, initial references, protected original files and environment integrity. It explicitly stated statistics_recomputed=false, so this verification adds the previously uncovered independent arithmetic check. It does not repeat the environment scan.

Prior receipt: `D:\dt-talk\DT_LIFECYCLE_ESCALATION\verification\paper3_canonical_inputs\replication_dynamic_delivery_recovery_v4\FINAL_READONLY_ACCEPTANCE_004.json`; SHA256 `c4229bcd5f46612c5bb062412f1f2f308ea8ef44cda8fca9a12c5143cf003e64`.
Numerical source: `D:\dt-talk\DT_LIFECYCLE_ESCALATION\results\p7_7_integrity_replication_batch20_env_v3\statistics_batch20_env_v3`; complete input paths and SHA256 are in STATISTICS_INPUT_INDEX.json and RAW_CSV_INDEX.json.

All 1200 CSV files (28800 rows) were each read once into a hash-checked buffer matched to their receipt and saved statistics manifest. All sixteen saved numerical outputs, including every 20000 method and 16000 paired bootstrap row, matched the independent calculations. Numeric comparisons use absolute tolerance 1e-14 and relative tolerance 1e-12; categorical fields and all 80000 bootstrap indices match exactly.

## Method means and rates

| Method | Mean service loss | Gate-open rate | RI rate |
|---|---:|---:|---:|
| B0 | 0.0066047987355432273 | 0 | 0 |
| B1 | 0.0033419799126224664 | 0 | 0 |
| B2 | 0.0048839414725433822 | 0 | 0 |
| B8 | 0.0029126269437559434 | 1 | 0.018229166666666664 |
| P7.7 | 0.002940643859084149 | 0.33298611111111109 | 0.018055555555555554 |

## Observed paired contrasts

| Contrast | Observed difference | 95% interval |
|---|---:|---|
| P7.7 - B0 | -0.0036641548764590783 | [-0.0045738278224222188, -0.0028134015487948244] |
| P7.7 - B1 | -0.00040133605353831741 | [-0.00054351944342202936, -0.00027324824378676267] |
| P7.7 - B2 | -0.0019432976134592331 | [-0.0022800258030189167, -0.0016164860065722071] |
| P7.7 - B8 | 2.8016915328205657e-05 | [-1.8594825329880642e-07, 8.4236694237915783e-05] |

The P7.7-minus-B8 interval crosses zero. Neither superiority nor statistical equivalence is supported. The three other marginal paired intervals lie below zero; this is the saved 95% interval protocol, without a new multiplicity adjustment or a claim of simultaneous family-wise coverage.

## Protocol and scenario verification

The endpoint is the mean of 24 stage service losses, then the mean of 3 seeds and 4 scenarios within each center, then an equal mean over 20 centers. Action cost is reported separately and never added to the service-loss endpoint. Resampling uses center as the unit. NumPy default_rng(2904) generates exactly the saved 4000×20 int64 index matrix. The same draw matrix is reused jointly for all methods, paired differences, and descriptive scenario intervals. Percentile endpoints use linear 2.5% and 97.5% quantiles. Point estimates come from the original observed center means, not the mean of bootstrap replicates. All 80 leave-one-center-out contrasts also match.

| Method | C0 | C1 | C3 | C4 |
|---|---:|---:|---:|---:|
| B0 | 0.0029677385190249577 | 0.0055018908085306371 | 0.013005227748302182 | 0.0049443378663151325 |
| B1 | 0.0024897313197773958 | 0.0023792893820831929 | 0.0053288546640235124 | 0.0031700442846057642 |
| B2 | 0.0029036060506768989 | 0.0029353788273510872 | 0.0095633897710690179 | 0.0041333912410765252 |
| B8 | 0.0028481570255987918 | 0.0026760478573527912 | 0.0033109508967754664 | 0.0028153519952967246 |
| P7.7 | 0.0028481570255987918 | 0.0026689542417039367 | 0.0034232664890926877 | 0.0028221976799411804 |

All scenario action counts, rates, action costs and saved descriptive intervals were compared, not just the displayed means. C0 and C1 do not support a universal Proposed-wins-every-scenario claim.

## Search work and saved timer evidence

| Method | Candidate count total | Charged search updates | Actual attributed decision seconds | Standalone estimated seconds |
|---|---:|---:|---:|---:|
| B0 | 0 | 0 | 2202.5181463010667 | 2202.5181463010667 |
| B1 | 0 | 0 | 2296.6412864986924 | 2296.6412864986924 |
| B2 | 0 | 0 | 5370.8783286986873 | 5370.8783286986873 |
| B8 | 53280 | 2664000 | 34280.914582599944 | 34280.914582599944 |
| P7.7 | 17428 | 871400 | 15102.042184498539 | 15102.042184498539 |

Every stage satisfies charged RI updates = 50 × feasible candidate count. These are recorded eligible-candidate counts and charged algorithmic updates; 50 is per candidate and is not a global search budget. core/p7.py lines 299–310 define the cached decision-call attribution and the standalone estimate. All saved cache-hit counters are zero in this inventory, and these two runtime columns happen to agree. Their meanings remain distinct. Neither column measures full end-to-end experiment walltime, total CPU/GPU work, complete resource usage, or energy; those quantities are NOT_VERIFIED by these CSV timers.

## Offline diagnostics and denominators

| Metric | Count | Denominator | Rate |
|---|---:|---:|---:|
| correct retain | 407 | 5760 | 0.070659722222222221 |
| unnecessary RI | 12 | 5760 | 0.0020833333333333333 |
| correct escalation | 92 | 5760 | 0.015972222222222221 |
| missed escalation | 2100 | 5760 | 0.36458333333333331 |

unnecessary RI means action=ri and R_B50≥0. missed escalation means action≠ri and R_B50<0; it is not restricted to closed-gate cases. The denominator for both is all 5760 Proposed stages. The four masks may overlap and are not exhaustive. They use saved finite-reference offline labels, not verified online counterfactual outcomes. Missed escalation remains a method limitation.

## Scope and preservation

The original-versus-corrected tables also match their saved original summaries; no original inference was rerun and changes are not causal attribution. This remains an integrity-correction replication on previously observed inputs, not new unseen held-out evidence. Historical environment numerical equivalence remains NOT_VERIFIED. No manuscript section is automatically frozen.

Evidence implementation: verify_statistics.py. Detailed fresh comparisons: STATISTICS_VERIFICATION.json. Hash-bound source and input index: STATISTICS_INPUT_INDEX.json. Full raw paths and hashes (without copying raw CSV): RAW_CSV_INDEX.json.

## Statistical interpretation risk coverage — 11/11 reviewed

Interpretation status: ANALYZED. This table applies the ARS `experiment-agent/references/statistical_interpretation_guide.md` to the existing verification; it adds no analysis, test, changed protocol, or model run. Inference is at the **20-center** level, not 1200 independent trajectories or 28800 independent stages. The four reported paired **marginal 95% intervals are not simultaneous intervals** and do not establish family-wise 95% coverage. No new multiplicity-adjusted inference is claimed. The original-unit observed differences and their saved intervals are the effect evidence; no unsupported small/medium/large effect-size class or practical-equivalence margin is assigned. In particular, B8's interval crossing zero supports neither Proposed superiority nor statistical equivalence.

| Interpretation risk | Coverage | Evidence and remaining limit |
|---|---|---|
| 1. Simpson's paradox | Checked; heterogeneous directions retained | All four scenarios and the aggregate were compared. B1 has lower mean loss than Proposed in C0/C1, while the aggregate favors Proposed. The balanced aggregate is not a claim of benefit in every scenario; no reversal explanation is inferred. |
| 2. Ecological fallacy | Checked; inference limited | Center-level paired resampling preserves the inference unit of 20 centers. Aggregate differences do not establish benefit for every center, seed, trajectory, stage, or deployment. |
| 3. Berkson's paradox / selection bias | Limitation | All predefined 20 centers and all results are retained, without outcome-based exclusion. The canonical population is constrained and its inputs were previously observed; unrestricted population generalization and unseen-held-out status are not established. |
| 4. Collider bias | Not applicable to this contrast estimator; scope limited | Saved contrasts use paired center means without outcome-dependent covariate adjustment or conditioning on gate-open/RI subsets. This does not certify every downstream causal model a manuscript might propose. |
| 5. Base-rate neglect | Checked | Gate/RI rates use all method stages; both offline error-mask rates use all 5760 Proposed stages. The masks are not sensitivity, specificity, precision, or conditional error rates and are potentially overlapping/nonexhaustive. |
| 6. Regression to the mean | Not applicable to the primary estimator | Primary comparisons are paired method outcomes over the fixed complete matrix, not uncontrolled before-after improvement in a subgroup selected for extreme observed loss. Original-versus-corrected changes remain descriptive. |
| 7. Survivorship bias | Checked within the authorized matrix | 1200/1200 trajectories and all 240 five-method groups are retained; no favorable-only completion subset is used. Failed/interrupted execution history is preserved, and this check does not erase historical exit-observation gaps. |
| 8. Look-elsewhere effect | Checked reporting; multiplicity limitation | All four Proposed-minus-baseline contrasts, including adverse/zero-crossing B8, and all scenarios are included. Four marginal 95% intervals are not a joint or multiplicity-adjusted confidence statement. |
| 9. Garden of forking paths | Checked protocol; historical limitation | This verification follows the saved center/seed/scenario/4000-draw protocol exactly, without exclusions, endpoint changes, retuning, or new tests. Previously observed input/outcome history prevents a claim of fresh confirmatory held-out evidence. |
| 10. Correlation versus causation | Claim boundary retained | The controlled replication supports comparisons for the specified methods and frozen input protocol. Original-to-corrected changes do not identify causal attribution; deployment effects and offline-label counterfactual validity are not established. |
| 11. Reverse causality | Checked recorded order; interpretive limitation | The prior full causal/input audit is reused for decision-before-future-service ordering. The offline R_B50 label is a separate finite-reference diagnostic, not proof of an online causal mechanism or a universally valid recovery boundary. |
