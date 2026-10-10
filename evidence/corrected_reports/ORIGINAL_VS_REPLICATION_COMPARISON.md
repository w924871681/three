# Original vs Replication Comparison

Repository: `D:\dt-talk\DT_LIFECYCLE_ESCALATION`. Results: `D:\dt-talk\DT_LIFECYCLE_ESCALATION\results\p7_7_integrity_replication_batch20_env_v3`. Replication digest `7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea`. F1 bundle `ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228`. Saved statistics receipt: `D:\dt-talk\DT_LIFECYCLE_ESCALATION\results\p7_7_integrity_replication_batch20_env_v3\statistics_batch20_env_v3\statistics_execution_receipt.json`. All numeric table strings below come from saved, hash-bound CSV cells; no statistic was recalculated by this report generator. **This delivery is valid only with the final COMPLETED DELIVERY_MANIFEST.json binding the exact report SHA.**

| method | original_mixed_inventory_mean | corrected_batch20_mean | corrected_minus_original | original_ci_low | original_ci_high | corrected_ci_low | corrected_ci_high | causal_attribution |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0 | 0.006049676514516644 | 0.006604798735543227 | 0.0005551222210265832 | 0.00473828067350874 | 0.007475796475300596 | 0.005033902315067533 | 0.008255700132237712 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B1 | 0.002985070205270142 | 0.0033419799126224664 | 0.0003569097073523246 | 0.002286870119930367 | 0.0037692499721896982 | 0.0025065074416425488 | 0.004257924875520683 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B2 | 0.004535350747396975 | 0.004883941472543382 | 0.0003485907251464075 | 0.0036400970088777676 | 0.005557066298132043 | 0.0038601564234488693 | 0.005979564093428911 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B8 | 0.0024859688219723572 | 0.0029126269437559434 | 0.00042665812178358615 | 0.0018613954531421946 | 0.0031797523427849156 | 0.002168176367251312 | 0.003709445781764266 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| P7.7 | 0.002524255871657655 | 0.002940643859084149 | 0.00041638798742649414 | 0.001877003560423972 | 0.003252184798338037 | 0.002189337225937733 | 0.0037421774917814014 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |

| method | scenario | original_mixed_inventory_mean | corrected_batch20_mean | corrected_minus_original | causal_attribution |
| --- | --- | --- | --- | --- | --- |
| B0 | C0 | 0.002615431663070912 | 0.0029677385190249577 | 0.00035230685595404564 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B0 | C1 | 0.0051702075418587614 | 0.005501890808530637 | 0.0003316832666718757 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B0 | C3 | 0.012172532316455736 | 0.013005227748302182 | 0.0008326954318464454 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B0 | C4 | 0.004240534536681166 | 0.0049443378663151325 | 0.0007038033296339662 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B1 | C0 | 0.0020945711266297825 | 0.0024897313197773958 | 0.0003951601931476132 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B1 | C1 | 0.00203655827163957 | 0.002379289382083193 | 0.00034273111044362276 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B1 | C3 | 0.005116946711718296 | 0.0053288546640235124 | 0.00021190795230521635 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B1 | C4 | 0.0026922047110929173 | 0.003170044284605764 | 0.0004778395735128469 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B2 | C0 | 0.0025065062120928623 | 0.002903606050676899 | 0.00039709983858403656 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B2 | C1 | 0.002547743572176832 | 0.002935378827351087 | 0.0003876352551742553 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B2 | C3 | 0.009496790749916616 | 0.009563389771069018 | 6.659902115240153e-05 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B2 | C4 | 0.0035903624554015855 | 0.004133391241076525 | 0.0005430287856749397 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B8 | C0 | 0.0024367662204895072 | 0.0028481570255987918 | 0.00041139080510928456 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B8 | C1 | 0.0023029941268052525 | 0.002676047857352791 | 0.0003730537305475386 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B8 | C3 | 0.0027728007816727263 | 0.0033109508967754664 | 0.0005381501151027401 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| B8 | C4 | 0.0024313141589219415 | 0.0028153519952967246 | 0.00038403783637478307 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| P7.7 | C0 | 0.0024367662204895072 | 0.0028481570255987918 | 0.00041139080510928456 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| P7.7 | C1 | 0.0023029941268052525 | 0.0026689542417039367 | 0.0003659601148986841 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| P7.7 | C3 | 0.002885116373989947 | 0.0034232664890926877 | 0.0005381501151027405 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |
| P7.7 | C4 | 0.002472146765345912 | 0.0028221976799411804 | 0.00035005091459526863 | NOT_IDENTIFIED_FROM_MEAN_CHANGE |

| comparison | original_observed_method_mean_difference | corrected_observed_method_mean_difference | corrected_minus_original_difference | corrected_ci_low | corrected_ci_high | original_paired_inference_scope | new_heldout_is_unseen | causal_attribution |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P7.7 - B0 | -0.003525420642858989 | -0.0036641548764590783 | -0.0001387342336000891 | -0.004573827822422219 | -0.0028134015487948244 | 239 matched groups; one group mismatch; mixed canonical population | False | NOT_IDENTIFIED_FROM_CONTRAST_CHANGE |
| P7.7 - B1 | -0.00046081433361248696 | -0.0004013360535383174 | 5.947828007416955e-05 | -0.0005435194434220294 | -0.00027324824378676267 | 239 matched groups; one group mismatch; mixed canonical population | False | NOT_IDENTIFIED_FROM_CONTRAST_CHANGE |
| P7.7 - B2 | -0.0020110948757393198 | -0.0019432976134592331 | 6.779726228008662e-05 | -0.0022800258030189167 | -0.001616486006572207 | 239 matched groups; one group mismatch; mixed canonical population | False | NOT_IDENTIFIED_FROM_CONTRAST_CHANGE |
| P7.7 - B8 | 3.828704968529767e-05 | 2.8016915328205657e-05 | -1.0270134357092016e-05 | -1.8594825329880642e-07 | 8.423669423791578e-05 | 239 matched groups; one group mismatch; mixed canonical population | False | NOT_IDENTIFIED_FROM_CONTRAST_CHANGE |

All differences above were already computed and saved by the independently receipted statistics stage. No direction is used to choose dependencies, stop execution or alter reporting. Mean change cannot identify a cause: canonical materialization, stochastic original method paths and the approved independent runtime are not isolated intervention factors. Original239 F/961 S mixed provenance and one cross-method mismatching group prevent treating the old full inventory as a completely canonical paired population. Original files and original CIs remain intact and are not replaced by these reports.

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
