# Scientific Claim Boundary — Paper 3 Final Evidence Archive

Paper: *Bounded Maintenance Recoverability for Selective Lifecycle Escalation of Digital-Twin Models*.

This is a scientific-review boundary document for the saved **integrity-correction replication**. It does not amend frozen algorithms, labels, thresholds, estimators, centers or statistical protocols. It does not freeze Sections 3–4, the complete manuscript, deployment validity or submission readiness.

## Prior verification reused

The completed independent v4 acceptance inspected the complete 1200 trajectories, 240 five-method groups and 28,800 stage records; verified 2535 protected original files and 13,192 runtime-bound files; and checked saved statistics and delivery bytes. This prose task reuses that actual completed audit rather than repeating the full scan. Its scope is scientific artifacts and new metadata finalization, not a claim that every historical process exit is known. Evidence: [FINAL_READONLY_ACCEPTANCE_004.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/replication_dynamic_delivery_recovery_v4/FINAL_READONLY_ACCEPTANCE_004.json>) (SHA256 `c4229bcd5f46612c5bb062412f1f2f308ea8ef44cda8fca9a12c5143cf003e64`); actual exit 0: [FINAL_READONLY_ACCEPTANCE_ACTUAL_EXIT_004.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/replication_dynamic_delivery_recovery_v4/FINAL_READONLY_ACCEPTANCE_ACTUAL_EXIT_004.json>) (SHA256 `54fbe12b4f12cd75e517f9cd8b1235dce442b890123a97a5c26a05e056228396`).

## Mathematical and operational objects must remain distinct

| Object or rule | Supported interpretation | Claim not established by the saved experiment |
|---|---|---|
| C1 theoretical maintenance recoverability | A quantity defined for the paper's theoretical maintenance policy class, horizon and resource assumptions | Identity with a finite, one-shot empirical reference policy set |
| Finite reference label `R_B50` | Frozen threshold minus the best observed offline horizon loss among the fixed P0/P10/P20/P50 reference procedures; effective horizon `H_t = min(4, 25-t)` | Exhaustive optimization over every policy in the theoretical C1 class; proof of absolute inability to maintain |
| A1 supervised target and online score | A1 is trained against normalized reference evidence `R_B50/S_m`; online inference is a prediction from same-identity causal response features | Equality of a predicted score to its supervised label, the true finite reference margin or the theoretical recoverability quantity |
| Positive identity-held scale `S_m` | The frozen scale is the floored median of 104 errors from the permitted 200-observation deployment reference; positive scaling preserves the sign of the exact label | Guaranteed sign agreement for an imperfect learned prediction |
| `q < 0` (negative A1 operational score) | Makes the fixed-bank RI search admissible under the frozen online rule; the eventual action still follows feasibility, costs, comparison and fallback | A theorem that current-model maintenance is impossible; a requirement to perform RI |
| 50 candidate updates | Exactly 50 frozen adaptation updates for each feasible candidate; a local per-candidate allowance | A total global search budget of 50 updates across all candidates, stages and probe work |

The frozen online implementation and label construction are evidenced by [p6.py](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/core/p6.py>) (SHA256 `7597861c7bddd8e32080a3f83eff0ab0bc0f55db6c6b11aec773794f33cc2b07`), [p7.py](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/core/p7.py>) (SHA256 `378f2b8644f97e87fa819661da694d1bfcb163e7d183d110edf5f08c9d6dfe3d`) and [P7_7_FINAL_LIFECYCLE_PROTOCOL.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json>) (SHA256 `6339a9247b984b497d1543198b3a7b7c0cfdf9c7bcfd1c52b47b62e17d2fd0df`). The current corrected scientific decision explicitly retains the unresolved theoretical/empirical/online distinction: [SCIENTIFIC_FREEZE_DECISION.md](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001/corrected_reports/SCIENTIFIC_FREEZE_DECISION.md>) (SHA256 `0490fb0517e8257f96e2a1c88dd9c99a39d0bdbf5d107a9666f80df0bee6b212`). Earlier integration text's use of “unrecoverable” at the zero boundary must not be promoted into proof that a learned online negative score establishes theoretical nonrecoverability. This archive states the boundary; it does not silently rewrite the core definition.

## Service-loss evidence and its inference scope

The saved primary endpoint is mean lifecycle service loss: stage mean within trajectory, then seed/scenario mean within each center, then arithmetic mean over 20 centers. The frozen joint paired bootstrap uses 4000 resamples, seed 2904 and shared resampled center indices across all methods; the observed contrast uses original center means, not the mean of bootstrap replicates.

| Contrast | Observed Proposed-minus-baseline difference | Saved 95% percentile interval | Permitted statement |
|---|---:|---|---|
| P7.7 − B0 | -0.0036641548764590783 | [-0.004573827822422219, -0.0028134015487948244] | Lower mean service loss under this fixed protocol and interval procedure |
| P7.7 − B1 | -0.0004013360535383174 | [-0.0005435194434220294, -0.00027324824378676267] | Lower mean service loss under this fixed protocol and interval procedure |
| P7.7 − B2 | -0.0019432976134592331 | [-0.0022800258030189167, -0.001616486006572207] | Lower mean service loss under this fixed protocol and interval procedure |
| P7.7 − B8 | +0.000028016915328205657 | [-0.00000018594825329880642, +0.00008423669423791578] | The interval crosses zero; superiority is not established |

Thus Proposed significantly lowers service loss relative to B0/B1/B2 in the sense of these specified 95% bootstrap intervals excluding zero. This is not an additional multiplicity-adjusted familywise claim. The B8 point difference is slightly adverse and its interval crosses zero. **No Proposed superiority over B8 and no statistical equivalence or noninferiority are established.** No equivalence margin or equivalence test is introduced after observing the results.

All four scenarios C0/C1/C3/C4 remain reportable. Overall contrasts must not be presented as a win in every scenario: B1 has lower observed loss than P7.7 in C0 and C1. All adverse and zero-crossing results are retained. Numerical evidence: [CORRECTED_FINAL_STATISTICS.md](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001/corrected_reports/CORRECTED_FINAL_STATISTICS.md>) (SHA256 `77d58be3329be332916967bc51e779f16c1b11b22542207e2c50055b717963fc`); statistical source: [statistics.py](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/verification/paper3_canonical_inputs/replication_statistics_batch20_env_v3/statistics.py>) (SHA256 `5ccda537c83bf88f7531eeee7c9b4b82a55b23f4ba81b3c031b978ac8375e33c`); actual saved receipt: [statistics_execution_receipt.json](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/results/p7_7_integrity_replication_batch20_env_v3/statistics_batch20_env_v3/statistics_execution_receipt.json>) (SHA256 `82585cf06c15e2bebc2d37bea90ccb9b6f24aa78745c00f6fd3378a0a0742dec`).

## Search workload, recorded time and costs

P7.7 records 17,428 feasible candidates and 871,400 charged search updates; B8 records 53,280 candidates and 2,664,000 updates. Candidate counts and the `50 × count` charged update measure show reduced recorded search workload. They do not alone establish a corresponding end-to-end wall-clock, energy, financial or deployment cost improvement.

The saved totals are P7.7 `decision_runtime_actual_s = 15102.04218449854` and B8 `34280.914582599944`. The saved standalone-estimate totals happen to equal these recorded totals in this run. They remain semantically separate columns. Actual decision timers attribute work under the implemented execution/cache policy; standalone estimates reconstruct a different accounting convention. Neither is a dedicated controlled end-to-end benchmark including all initialization, loading, resource waiting, validation and packaging. The action cost ratio 10 and event penalties also remain model decision parameters, not measured hardware cost. See `core/p7.py` timer attribution and the corrected statistics report above.

## Missed escalation remains a method limitation

The frozen offline diagnostic denominator is **5760 Proposed stage records** (240 trajectories × 24 stages), not the number of open gates, RI actions or negative labels. “Missed escalation” is `action != 'ri' and R_B50 < 0`: 2100/5760 = 0.3645833333333333. “Unnecessary RI” is `action == 'ri' and not (R_B50 < 0)`: 12/5760 = 0.0020833333333333333. The labels are finite offline reference diagnostics, evaluated after decision sealing; they are not online inputs or ground-truth counterfactual deployment outcomes. In particular, missed escalation is not exclusively a closed-gate error because RI may be admissible but rejected by costs, feasibility or fallback. The four stored diagnostic masks are potentially overlapping and nonexhaustive and must not be presented as an exhaustive confusion matrix. This observed missed-escalation rate remains a material limitation.

## Population, environment and execution scope

This uses the already observed canonical F1 batch20 population in a controlled corrective replication. It is not a previously unseen held-out experiment. Historical complete runtime/numerical equivalence remains **NOT_VERIFIED**. Input/initial-state/deployment parity does not imply model outputs are invariant bit for bit under every worker schedule or Torch RNG history. Differences from the original mixed F/S population cannot identify the separate causal contributions of materialization, runtime and stochastic execution.

Bridge smoke started two workers; only DW0001 completed its one prespecified B1 trajectory and DW0002 received no TASK. Both saved worker exits are zero. A_FULL_0001's lost terminal cause/code remain NOT_VERIFIED; A_FULL_0002's intentional cutover remains an interruption. The later metadata producer PID 10108 has exit **NOT_OBSERVED** after its observer failed; new read-only finalizer PID 30796 and final v4 auditor PID 12964 have their own actual exit-0 receipts. Their success does not reconstruct PID 10108's historical exit. These boundaries are preserved in `SOURCE_ENVIRONMENT_PROVENANCE.md` and its indexed evidence.
