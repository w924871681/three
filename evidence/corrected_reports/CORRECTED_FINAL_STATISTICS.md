# Corrected Final Statistics

COMPLETED;1200/1200 trajectories;240/240 groups;60/60 initial references;2535 original protected files unchanged.

Repository: `D:\dt-talk\DT_LIFECYCLE_ESCALATION`. Results: `D:\dt-talk\DT_LIFECYCLE_ESCALATION\results\p7_7_integrity_replication_batch20_env_v3`. Replication digest `7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea`. F1 bundle `ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228`. Saved statistics receipt: `D:\dt-talk\DT_LIFECYCLE_ESCALATION\results\p7_7_integrity_replication_batch20_env_v3\statistics_batch20_env_v3\statistics_execution_receipt.json`. All numeric table strings below come from saved, hash-bound CSV cells; no statistic was recalculated by this report generator. **This delivery is valid only with the final COMPLETED DELIVERY_MANIFEST.json binding the exact report SHA.**

## All five methods and lifecycle actions

| method | mean_lifecycle_service_loss | ci_low | ci_high | n_centers | maintenance_count | maintenance_rate | ri_count | ri_rate | maintenance_cost | ri_cost | total_action_cost | retain_rate | gate_open_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 | 0.006604798735543227 | 0.005033902315067533 | 0.008255700132237712 | 20 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 |
| B1 | 0.0033419799126224664 | 0.0025065074416425488 | 0.004257924875520683 | 20 | 24.0 | 1.0 | 0.0 | 0.0 | 0.0058354605396743866 | 0.0 | 0.0058354605396743866 | 0.0 | 0.0 |
| B2 | 0.004883941472543382 | 0.0038601564234488693 | 0.005979564093428911 | 20 | 6.929166666666667 | 0.2887152777777778 | 0.0 | 0.0 | 0.0016847866106733517 | 0.0 | 0.0016847866106733517 | 0.7112847222222223 | 0.0 |
| B8 | 0.0029126269437559434 | 0.002168176367251312 | 0.003709445781764266 | 20 | 2.975 | 0.12395833333333332 | 0.4375 | 0.018229166666666664 | 0.0007233539627304709 | 0.00106375582754481 | 0.0017871097902752808 | 0.8578125 | 1.0 |
| P7.7 | 0.002940643859084149 | 0.002189337225937733 | 0.0037421774917814014 | 20 | 3.020833333333333 | 0.12586805555555555 | 0.4333333333333333 | 0.018055555555555554 | 0.0007344980713999879 | 0.0010536248196634308 | 0.0017881228910634189 | 0.8560763888888889 | 0.3329861111111111 |

## All four observed Proposed-minus-baseline contrasts

| comparison | mean_difference | ci_low | ci_high | n_centers | bootstrap_resamples | bootstrap_seed | point_estimate_source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P7.7 - B0 | -0.0036641548764590783 | -0.004573827822422219 | -0.0028134015487948244 | 20 | 4000 | 2904 | OBSERVED_METHOD_CENTER_MEAN_SUBTRACTION |
| P7.7 - B1 | -0.0004013360535383174 | -0.0005435194434220294 | -0.00027324824378676267 | 20 | 4000 | 2904 | OBSERVED_METHOD_CENTER_MEAN_SUBTRACTION |
| P7.7 - B2 | -0.0019432976134592331 | -0.0022800258030189167 | -0.001616486006572207 | 20 | 4000 | 2904 | OBSERVED_METHOD_CENTER_MEAN_SUBTRACTION |
| P7.7 - B8 | 2.8016915328205657e-05 | -1.8594825329880642e-07 | 8.423669423791578e-05 | 20 | 4000 | 2904 | OBSERVED_METHOD_CENTER_MEAN_SUBTRACTION |

Negative observed differences favor Proposed service loss; positive differences are adverse. Intervals including zero do not establish a directional difference. All four are retained regardless of sign or significance. No bootstrap replicate mean replaces the observed effect.

## All four scenarios for all five methods

| method | scenario | n_centers | lifecycle_service_loss | maintenance_count | maintenance_rate | ri_count | ri_rate | maintenance_cost | ri_cost | total_action_cost | retain_rate | gate_open_rate | ci_low | ci_high | ci_scope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 | C0 | 20 | 0.0029677385190249577 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0021513919983954114 | 0.0038584809885034905 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| B0 | C1 | 20 | 0.005501890808530637 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.004215176334701532 | 0.006786591578539729 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| B0 | C3 | 20 | 0.013005227748302182 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.01026285333601057 | 0.01598163196967562 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| B0 | C4 | 20 | 0.0049443378663151325 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 0.0 | 0.0032257076614910654 | 0.0067828413889002275 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| B1 | C0 | 20 | 0.0024897313197773958 | 24.0 | 1.0 | 0.0 | 0.0 | 0.0058354605396743866 | 0.0 | 0.0058354605396743866 | 0.0 | 0.0 | 0.0017622481989469127 | 0.003293954625832561 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| B1 | C1 | 20 | 0.002379289382083193 | 24.0 | 1.0 | 0.0 | 0.0 | 0.0058354605396743866 | 0.0 | 0.0058354605396743866 | 0.0 | 0.0 | 0.0017222808864794889 | 0.0030959003040076523 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| B1 | C3 | 20 | 0.0053288546640235124 | 24.0 | 1.0 | 0.0 | 0.0 | 0.0058354605396743866 | 0.0 | 0.0058354605396743866 | 0.0 | 0.0 | 0.004273504935896299 | 0.006441385599122846 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| B1 | C4 | 20 | 0.003170044284605764 | 24.0 | 1.0 | 0.0 | 0.0 | 0.0058354605396743866 | 0.0 | 0.0058354605396743866 | 0.0 | 0.0 | 0.002166302112353959 | 0.004248527320354091 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| B2 | C0 | 20 | 0.002903606050676899 | 2.6333333333333333 | 0.10972222222222221 | 0.0 | 0.0 | 0.0006402796981031619 | 0.0 | 0.0006402796981031619 | 0.8902777777777778 | 0.0 | 0.002113984402379477 | 0.0037639928280795067 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| B2 | C1 | 20 | 0.002935378827351087 | 6.716666666666667 | 0.2798611111111111 | 0.0 | 0.0 | 0.0016331184704783178 | 0.0 | 0.0016331184704783178 | 0.7201388888888889 | 0.0 | 0.0021942931643560665 | 0.0037357532797876857 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| B2 | C3 | 20 | 0.009563389771069018 | 9.5 | 0.39583333333333337 | 0.0 | 0.0 | 0.002309869796954445 | 0.0 | 0.002309869796954445 | 0.6041666666666666 | 0.0 | 0.008105362926728756 | 0.011097428126266904 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| B2 | C4 | 20 | 0.004133391241076525 | 8.866666666666667 | 0.36944444444444446 | 0.0 | 0.0 | 0.002155878477157482 | 0.0 | 0.002155878477157482 | 0.6305555555555555 | 0.0 | 0.0028176107592344127 | 0.005539689181677103 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| B8 | C0 | 20 | 0.0028481570255987918 | 1.45 | 0.06041666666666666 | 0.0 | 0.0 | 0.00035255907427199416 | 0.0 | 0.00035255907427199416 | 0.9395833333333334 | 1.0 | 0.0020802448624342813 | 0.003680249938732029 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| B8 | C1 | 20 | 0.002676047857352791 | 5.25 | 0.21875 | 0.016666666666666666 | 0.0006944444444444444 | 0.001276506993053772 | 4.052403152551657e-05 | 0.0013170310245792887 | 0.7805555555555556 | 1.0 | 0.002004112571375016 | 0.0034070302386226105 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| B8 | C3 | 20 | 0.0033109508967754664 | 3.3666666666666663 | 0.14027777777777778 | 1.05 | 0.04375 | 0.0008185854368154349 | 0.002553013986107544 | 0.0033715994229229786 | 0.8159722222222221 | 1.0 | 0.002434113906413889 | 0.004215649491104867 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| B8 | C4 | 20 | 0.0028153519952967246 | 1.8333333333333333 | 0.07638888888888888 | 0.6833333333333333 | 0.02847222222222222 | 0.00044576434678068237 | 0.0016614852925461794 | 0.0021072496393268617 | 0.8951388888888889 | 1.0 | 0.002097232582190271 | 0.0036001398796684553 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| P7.7 | C0 | 20 | 0.0028481570255987918 | 1.45 | 0.06041666666666666 | 0.0 | 0.0 | 0.00035255907427199416 | 0.0 | 0.00035255907427199416 | 0.9395833333333334 | 0.40902777777777777 | 0.0020802448624342813 | 0.003680249938732029 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| P7.7 | C1 | 20 | 0.0026689542417039367 | 5.266666666666667 | 0.21944444444444447 | 0.0 | 0.0 | 0.0012805593962063237 | 0.0 | 0.0012805593962063237 | 0.7805555555555556 | 0.2743055555555556 | 0.001998312560903691 | 0.003399904709492855 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| P7.7 | C3 | 20 | 0.0034232664890926877 | 3.5333333333333337 | 0.14722222222222223 | 1.05 | 0.04375 | 0.0008591094683409514 | 0.002553013986107544 | 0.003412123454448495 | 0.8090277777777779 | 0.3375 | 0.0025182235328540833 | 0.004372535389833907 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |
| P7.7 | C4 | 20 | 0.0028221976799411804 | 1.8333333333333333 | 0.07638888888888888 | 0.6833333333333333 | 0.02847222222222222 | 0.00044576434678068237 | 0.0016614852925461794 | 0.0021072496393268617 | 0.8951388888888889 | 0.3111111111111111 | 0.002103208055476797 | 0.003604612616915499 | ADDITIONAL_CENTER_LEVEL_DESCRIPTIVE_STRATUM_INTERVAL |

## All four frozen offline-label diagnostics

| metric | count | rate | denominator |
| --- | --- | --- | --- |
| correct retain | 407 | 0.07065972222222222 | 5760 |
| unnecessary RI | 12 | 0.0020833333333333333 | 5760 |
| correct escalation | 92 | 0.01597222222222222 | 5760 |
| missed escalation | 2100 | 0.3645833333333333 | 5760 |

These masks are potentially overlapping and nonexhaustive; missed escalation is action != ri and R_B50 <0, not solely a closed-gate error.

## Actual saved cost/search summaries

| method | n_centers | n_trajectories | n_stage_records | feasible_candidate_count_total_recorded | feasible_candidate_count_mean_trajectory_center_averaged | ri_search_updates_charged_total_recorded | ri_search_updates_charged_mean_trajectory_center_averaged | source_cache_hits_total_recorded | source_cache_hits_mean_trajectory_center_averaged | shared_parent_cache_hit_total_recorded | shared_parent_cache_hit_mean_trajectory_center_averaged | decision_runtime_actual_s_total_recorded | decision_runtime_actual_s_mean_trajectory_center_averaged | decision_runtime_standalone_estimate_s_total_recorded | decision_runtime_standalone_estimate_s_mean_trajectory_center_averaged |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 | 20 | 240 | 5760 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 2202.5181463010667 | 9.177158942921112 | 2202.5181463010667 | 9.177158942921112 |
| B1 | 20 | 240 | 5760 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 2296.6412864986924 | 9.569338693744552 | 2296.6412864986924 | 9.569338693744552 |
| B2 | 20 | 240 | 5760 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 5370.878328698687 | 22.378659702911197 | 5370.878328698687 | 22.378659702911197 |
| B8 | 20 | 240 | 5760 | 53280.0 | 222.0 | 2664000.0 | 11100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 34280.914582599944 | 142.83714409416643 | 34280.914582599944 | 142.83714409416643 |
| P7.7 | 20 | 240 | 5760 | 17428.0 | 72.61666666666666 | 871400.0 | 3630.8333333333335 | 0.0 | 0.0 | 0.0 | 0.0 | 15102.04218449854 | 62.92517576874392 | 15102.04218449854 | 62.92517576874392 |

This is an integrity-correction independent replication after original outcomes were observed. It is not an unseen or newly held-out evaluation. Historical final runtime equivalence is NOT_VERIFIED; the authorized independent runtime uses pandas2.3.3/River0.23.0/psutil7.2.2 and binds other frozen scientific dependencies. Frozen original Torch dropout/global RNG remains part of the original method; exact failed-task RNG evidence supports controlled retry, while universal scheduling-invariant stochastic paths are not asserted. Paired input/initial/deployment integrity does not remove that limitation. No estimator refit, threshold adjustment, model-bank change or population reselection is authorized. Action penalties are not complete measured compute cost; cached-call timers, standalone estimates and search counters remain distinct. Python audited IO/causal guards are evidence of the controlled paths, not a general native-library or operating-system sandbox proof. Section3–4 remain subject to the prior manuscript audit: theoretical C1 policy class is not identical to the one-shot P0/10/20/50 offline margin, nor is that margin identical to the normalized MLP online decision score; required paper-only bridging remains unresolved. H_t=min(4,25-t) and the50-update allowance per candidate must not be described as an overall search budget. The old S3–4 audit's characterization of239/961 as merely execution lineage is superseded by the later single-group forensic audit and actual StageB full-batch/singleton input verification. Scientific integrity PASS certifies the replication evidence; it does not automatically freeze Sections3–4, the whole paper, superiority, deployment validity or publication readiness.


## Dynamic execution provenance

Original successful V3 records were retained. The first 123 trajectories used one worker; additional static full_002 records and the real bridge smoke are included in the retained inventory. The FULL dynamic contract retained 332 trajectories and completed 868 with an outcome-blind resource policy capped at three workers. All original failed or interrupted attempts remain preserved. External observer finished timestamps are observation cutoffs; earlier actor/actual exit evidence remains NOT_VERIFIED where applicable. Actual dynamic coordinator and worker exits were observed by their owning Popen objects. No scheduling-invariant or bitwise stochastic output claim is made. The dynamic certificate is separate from old static phase success.


## Metadata erratum: smoke process count

The bridge smoke started two worker processes (DW0001 and DW0002). DW0001 alone owned and completed the one predeclared B1 trajectory; DW0002 received no TASK claim and completed a boundary STOP with zero assigned trajectories. Both owning backend actual exit receipts report zero and validate the finished receipts. The earlier smoke phase worker_count=1 was inaccurate for the actual started process count; one worker performed the one trajectory. The corrected phase table states "2 started / 1 trajectory worker". All saved statistical bytes, scientific gates, trajectory receipts, canonical V1 reports, original V1 package and ZIP are preserved. This correction changes execution metadata only and asserts no scheduling-invariant or bitwise stochastic output equivalence.

## Current corrected report file index

Use these six independently corrected reports:

- [EXECUTION_SUMMARY.md](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001/corrected_reports/EXECUTION_SUMMARY.md>) — `D:\dt-talk\DT_LIFECYCLE_ESCALATION\handoffs\PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001\corrected_reports\EXECUTION_SUMMARY.md`
- [INPUT_PARITY_AUDIT.md](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001/corrected_reports/INPUT_PARITY_AUDIT.md>) — `D:\dt-talk\DT_LIFECYCLE_ESCALATION\handoffs\PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001\corrected_reports\INPUT_PARITY_AUDIT.md`
- [EXPERIMENT_INTEGRITY_AUDIT.md](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001/corrected_reports/EXPERIMENT_INTEGRITY_AUDIT.md>) — `D:\dt-talk\DT_LIFECYCLE_ESCALATION\handoffs\PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001\corrected_reports\EXPERIMENT_INTEGRITY_AUDIT.md`
- [CORRECTED_FINAL_STATISTICS.md](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001/corrected_reports/CORRECTED_FINAL_STATISTICS.md>) — `D:\dt-talk\DT_LIFECYCLE_ESCALATION\handoffs\PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001\corrected_reports\CORRECTED_FINAL_STATISTICS.md`
- [ORIGINAL_VS_REPLICATION_COMPARISON.md](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001/corrected_reports/ORIGINAL_VS_REPLICATION_COMPARISON.md>) — `D:\dt-talk\DT_LIFECYCLE_ESCALATION\handoffs\PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001\corrected_reports\ORIGINAL_VS_REPLICATION_COMPARISON.md`
- [SCIENTIFIC_FREEZE_DECISION.md](<D:/dt-talk/DT_LIFECYCLE_ESCALATION/handoffs/PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001/corrected_reports/SCIENTIFIC_FREEZE_DECISION.md>) — `D:\dt-talk\DT_LIFECYCLE_ESCALATION\handoffs\PAPER3_DYNAMIC_REPLICATION_BATCH20_ENV_V3_A_DYNAMIC_0002_ERRATUM_001\corrected_reports\SCIENTIFIC_FREEZE_DECISION.md`
