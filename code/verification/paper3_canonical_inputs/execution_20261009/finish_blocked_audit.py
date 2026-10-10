"""Finalize honest BLOCKED delivery from existing evidence, using stdlib only.

This does not generate data, import project packages, run a model or calculate
statistics. Historical method means are copied verbatim from the existing CSV.
All publications are exclusive within this task's new output directories.
"""
import csv
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
EXEC = REPO / "verification/paper3_canonical_inputs/execution_20261009"
RESULTS = REPO / "results/p7_7_integrity_replication_batch20_v1"
CODE = REPO / "verification/paper3_canonical_inputs/replication_executor_batch20_v1"
INPUTS = REPO / "verification/paper3_canonical_inputs/P7_7_CANONICAL_INPUT_VERIFICATION_V1/CIV_INPUT_V1_AUTHORIZED_20261009_RUN003"
NOW = datetime.now(timezone.utc).isoformat()

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1048576),b""): h.update(chunk)
    return h.hexdigest()
def read(path): return json.loads(path.read_text(encoding="utf-8"))
def publish(path, data):
    if not (path.is_relative_to(RESULTS) or path.is_relative_to(EXEC)):
        raise RuntimeError("Delivery escaped authorized new directories")
    path.parent.mkdir(parents=True,exist_ok=True)
    payload = data if isinstance(data,str) else json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    with path.open("xb") as f: f.write(payload.encode("utf-8"))
def location(relative, pattern=None):
    path = REPO / relative
    if pattern is None: return f"`{path}`"
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    match = next(i for i,line in enumerate(lines,1) if pattern in line)
    return f"`{path}`:{match} (`{pattern}`)"

snapshot = read(EXEC/"original_protected_start_sha256.json")
errors = [name for name,expected in snapshot.items() if sha(REPO/name) != expected]
if errors: raise RuntimeError("Original protection failure: "+repr(errors))
old_audit = read(REPO/"audits/P7_7_FINAL_HELDOUT_SCIENTIFIC_AUDIT.json")
old_ledger = old_audit["output_hashes"]
ledger_errors = [name for name,expected in old_ledger.items() if sha(REPO/name) != expected]
if ledger_errors: raise RuntimeError("Historical output ledger differs")
old_raw = REPO/"results/p7_7/raw"
original_csv_count = len(list(old_raw.glob("*.csv")))
original_receipt_count = len(list(old_raw.glob("*.integrity.json")))
if (len(snapshot),len(old_ledger),original_csv_count,original_receipt_count) != (2535,1201,1200,1200):
    raise RuntimeError("Original coverage/count changed")
new_csv_count = len(list((RESULTS/"raw").glob("*.csv")))
new_receipt_count = len(list((RESULTS/"raw").glob("*.integrity.json")))
for item in ("provenance_manifest.json","initial_state_manifest.json","initial_states","workers","raw","execution"):
    if (RESULTS/item).exists(): raise RuntimeError("Unexpected model execution artifact; reconsider blocked inventory")
if new_csv_count or new_receipt_count: raise RuntimeError("Unexpected new trajectories")
a = read(EXEC/"stage_a_attempt_05_results.json")
b = read(EXEC/"stage_b_scientific_gate.json")
c = read(RESULTS/"stage_c_tests/attempt001/results.json")
if not a["all_42_pass"] or not b["execution_pass"] or not c["all_pass"]:
    raise RuntimeError("Reported software/input passes lack actual evidence")
actual_code = {p.relative_to(CODE).as_posix():sha(p) for p in sorted(CODE.rglob("*.py"))}
if actual_code != c["implementation_sha256"]: raise RuntimeError("Executor changed after tests")
f1 = read(INPUTS/"contexts/F1.json")
f2 = read(INPUTS/"contexts/F2.json")
s1 = read(INPUTS/"contexts/S1.json")
s2 = read(INPUTS/"contexts/S2.json")
for name,expected in f1["created_file_sha256"].items():
    if sha(INPUTS/name) != expected: raise RuntimeError("F1 input changed: "+name)
if f1["input_bundle_digest"] != f2["input_bundle_digest"] or s1["input_bundle_digest"] != s2["input_bundle_digest"]:
    raise RuntimeError("Repeatability mismatch")
failure = read(EXEC/"stage_c_prepare_observed_failure.json")
if failure["exit_code"] != 1 or failure["model_or_optimizer_executed"]:
    raise RuntimeError("Observed stop evidence differs")
source_env = read(INPUTS/"source_environment_manifest.json")
cfg = read(REPO/"configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json")
source_expected = source_env["sources"]
if not isinstance(source_expected,dict): raise RuntimeError("Unexpected Stage B source pin schema")
if not all(isinstance(v,str) and re.fullmatch("[a-f0-9]{64}",v) for v in source_expected.values()):
    raise RuntimeError("Source binding is not an exact SHA mapping")
for name,expected in {**source_expected,**cfg["source_bindings_sha256"]}.items():
    if sha(REPO/name) != expected: raise RuntimeError("Frozen source/config pin mismatch: "+name)
site = Path(source_env["environment"]["numpy_parent"])
required = {"numpy","torch","pandas","psutil","river","scipy","scikit-learn"}
distributions = {}
for file in sorted(site.glob("*.dist-info/METADATA")):
    text = file.read_text(encoding="utf-8")
    name = next((x[6:] for x in text.splitlines() if x.startswith("Name: ")),None)
    version = next((x[9:] for x in text.splitlines() if x.startswith("Version: ")),None)
    if name and name.lower().replace("_","-") in required:
        distributions[name.lower().replace("_","-")] = {"version":version,"path":str(file),"sha256":sha(file)}
missing = sorted(required-set(distributions))
if missing != ["psutil","river"]: raise RuntimeError("Missing dependency evidence changed")
base_site = Path(r"C:\Users\92487\anaconda3\Lib\site-packages")
wheel_evidence = {}
for name in ("river-0.23.0.dist-info","psutil-5.9.0.dist-info"):
    wheel = base_site/name/"WHEEL"
    wheel_evidence[name] = {"path":str(wheel),"sha256":sha(wheel),
        "tags":[line[5:] for line in wheel.read_text(encoding="utf-8").splitlines() if line.startswith("Tag: ")]}
git_cmd = ["git","--no-optional-locks","-C",str(REPO)]
git_head = subprocess.check_output(git_cmd+["rev-parse","HEAD"],text=True).strip()
git_tracked = subprocess.check_output(git_cmd+["status","--short","--untracked-files=no"],text=True)
if git_head != "436ee9960a32a8e94e571ded3fc800a2fa20f3e4": raise RuntimeError("Git HEAD changed")
if set(git_tracked.splitlines()) != {
    " M core/p7.py", " M reports/P7_7_FINAL_LIFECYCLE_PROTOCOL.md",
    " M reports/P7_7_FINAL_LIFECYCLE_PROTOCOL.md.sha256",
    " M results/p7_6b/task_states/fit/32248_7312_C1.json",
    " M results/p7_6b/task_states/fit/32248_7312_C3.json"}:
    raise RuntimeError("Tracked Git status differs from original task start")
protection = {"status":"VERIFIED","time_utc":NOW,"repo":str(REPO),"protected_files":len(snapshot),
    "all_original_bytes_unchanged":True,"original_csv_count":original_csv_count,
    "original_receipt_count":original_receipt_count,"historical_output_ledger_entries":len(old_ledger),
    "historical_output_ledger_matches":True,"new_csv_count":new_csv_count,"new_receipt_count":new_receipt_count,
    "git_HEAD":git_head,"git_tracked_status":git_tracked,"errors":[],
    "basis":str(EXEC/"original_protected_start_sha256.json"),"basis_sha256":sha(EXEC/"original_protected_start_sha256.json")}
publish(EXEC/"original_protected_final_check.json",protection)
publish(RESULTS/"ORIGINAL_PRESERVATION_FINAL_CHECK.json",protection)
dependencies = {"status":"BLOCKED","scope":"READ_ONLY_METADATA_NO_PACKAGE_IMPORT","python":source_env["environment"]["python_executable"],
    "python_version":source_env["environment"]["python_version"],"site_packages_root":str(site),"distributions":distributions,
    "missing_required_distributions":missing,"missing_package_directories":{name:not (site/name).exists() for name in missing},
    "alternative_base_wheel_evidence":wheel_evidence,"base_wheels_approved_for_this_interpreter":False,
    "historical_final_runtime_dependency_closure":"NOT_VERIFIED","installed_or_modified_any_dependency":False,
    "historical_requirements_path":str(REPO/"configs/requirements_frozen.txt"),"historical_requirements_sha256":sha(REPO/"configs/requirements_frozen.txt"),
    "historical_environment_path":str(REPO/"audits/environment.json"),"historical_environment_sha256":sha(REPO/"audits/environment.json")}
publish(RESULTS/"MODEL_ENVIRONMENT_BLOCKER_EVIDENCE.json",dependencies)
evidence_paths = [EXEC/"stage_a_attempt_05_results.json",EXEC/"STAGE_A_EXECUTED_AUDIT.md",EXEC/"stage_b_scientific_gate.json",
    EXEC/"stage_b_input_summary.json",EXEC/"stage_c_prepare_observed_failure.json",EXEC/"stage_c_prepare_attempt01.log",
    RESULTS/"stage_c_tests/attempt001/results.json",INPUTS/"execution_receipt.json",INPUTS/"run_manifest.json",
    INPUTS/"outputs_inventory.json",INPUTS/"source_environment_manifest.json",INPUTS/"contexts/F1.json",INPUTS/"contexts/F2.json",
    INPUTS/"contexts/S1.json",INPUTS/"contexts/S2.json",INPUTS/"validation_certificate.json",
    EXEC/"STAGE_C_STATIC_CROSS_REVIEW.md",EXEC/"stage_c_environment_blocker_review.md"]
evidence_manifest = {"schema":"paper3-blocked-delivery-evidence-manifest-v1","status":"BLOCKED","is_runnable_execution_manifest":False,
    "repo":str(REPO),"created_utc":NOW,"canonical_candidate_id":"P7_7_ORIGINAL_BATCH20_CANDIDATE_V1",
    "input_protocol_id":"P7_7_CANONICAL_INPUT_VERIFICATION_V1","input_bundle_F1_digest":f1["input_bundle_digest"],
    "input_bundle_S1_digest":s1["input_bundle_digest"],"input_definition_digest":f1["definition_digest"],
    "input_dependency_digest":f1["dependency_digest"],"F1_input_files_sha256":f1["created_file_sha256"],
    "source_pins_sha256":source_expected,"configuration_source_bindings_sha256":cfg["source_bindings_sha256"],
    "final_configuration_sha256":sha(REPO/"configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json"),
    "executor_implementation_sha256":actual_code,"evidence_sha256":{str(path):sha(path) for path in evidence_paths},
    "model_environment_freeze":"FAILED_NOT_PUBLISHED","R2":"NOT_VERIFIED","R3":"NOT_VERIFIED",
    "trajectories_completed":0,"five_method_groups_verified":0,"original_preservation":protection,
    "dependency_blocker":dependencies,"statistics_executed":False,"no_claim_of_unseen_heldout":True}
publish(RESULTS/"SOURCE_CONFIG_INPUT_EVIDENCE_MANIFEST.json",evidence_manifest)
publish(RESULTS/"PREPARE_FAILURE_OBSERVED.json",failure)
publish(RESULTS/"EXECUTION_STATUS.json",{"status":"BLOCKED","time_utc":NOW,"stage_A":"PASS_42",
    "stage_B":"PASS_INPUT_ONLY","stage_C_software_tests":"PASS_50","stage_C_environment_freeze":"BLOCKED",
    "initial_states_verified":0,"trajectories_completed":0,"trajectories_expected":1200,
    "paired_groups_verified":0,"paired_groups_expected":240,"stage_D":"NOT_STARTED","stage_E":"NOT_EXECUTED",
    "originals_preserved":True,"reason":"Required psutil and ABI-compatible River dependencies absent; no unauthorized environment change"})

common = f"""目标仓库：`{REPO}`。交付目录：`{RESULTS}`。状态：**BLOCKED**，新轨迹 **0/1200**；新五方法公平组 **0/240 已核验（全部待执行，不能称为已失败的配对）**。

本次不是性能失败。已完成软件测试和输入验证；模型环境冻结在任何 warm-up、模型执行、轨迹或统计之前停止。原始结果没有被替换，本文档不批准安装依赖、放松 import guard、删改冻结源码或跳过科学门槛。
"""
failure_refs = f"""- **VERIFIED**：{location('verification/paper3_canonical_inputs/replication_executor_batch20_v1/provenance.py','required scientific packages missing')}，`capture_model_environment` 要求完整依赖集合；实际 prepare 退出码 1。观察记录 `{EXEC / 'stage_c_prepare_observed_failure.json'}` 的 `exit_code/observed_stack`；stdout 日志只捕获哈希进度，stderr 取自实际已完成的 Codex 工具结果并明确标记转录。
- **VERIFIED**：{location('scripts/run_p7_7_final.py','import psutil')}，原 runner 必需导入 `psutil`；{location('core/p7.py','from river.drift import ADWIN')} 和 {location('scripts/run_p7.py','import river')} 必需导入 River；{location('scripts/run_p7.py','river.__version__')} 要求 River 0.23.0。
- **VERIFIED**：`{RESULTS / 'MODEL_ENVIRONMENT_BLOCKER_EVIDENCE.json'}`，`missing_required_distributions/missing_package_directories`：批准的 Python 3.11.15 单一 site root 中两项都缺失。替代 base 的两个 WHEEL 均含 `cp313-cp313-win_amd64`，不能作为当前 cp311 可用性的证明。
- **NOT_VERIFIED**：历史最终 runner 使用的完整解释器/依赖闭包；{location('configs/requirements_frozen.txt','numpy==')} 起的 36 行清单缺少这两项；`{REPO / 'audits/environment.json'}` 记录 rcf-dti-py311，但不包含最终 run identity、River/psutil 版本和完整依赖哈希。
"""
original_refs = f"""**VERIFIED**：`{RESULTS / 'ORIGINAL_PRESERVATION_FINAL_CHECK.json'}`：2535/2535 原保护文件 SHA 不变，原始 CSV 1200、receipts 1200；`{REPO / 'audits/P7_7_FINAL_HELDOUT_SCIENTIFIC_AUDIT.json'}` 的 1201 项 `output_hashes` 全部再次匹配。Git HEAD `{git_head}`；已有 tracked 修改与任务开始时一致：

```text
{git_tracked.rstrip()}
```

这些完成/字节证明不等于原实验 240 组均科学配对，也不证明总体来自统一 canonical batch。新增未跟踪文件仅为本次授权交付，不使用 Git checkout/reset/clean/add/commit。
"""
stage_b_refs = f"""**VERIFIED**：`{EXEC / 'stage_b_scientific_gate.json'}`，`execution_pass/cohorts`；旧 serial 239/239 对应恢复的 F reference，后续 parallel 961/961 对应 S reference。这里是保存输入字段的 R1 对应，不能提升为历史环境完全复现、初始参数实测或 R3 整体认证。

**VERIFIED**：`{INPUTS / 'execution_receipt.json'}`、`validation_certificate.json` 与 `contexts/F1.json/F2.json/S1.json/S2.json`：F1=F2、S1=S2；每上下文 20 base、80 scenarios、5760 stage roles、160 warm-up/reference 摘要。readonly 1/3 worker 与 canonical/reverse/permuted task-order、resume 检查通过。

F input bundle digest：`{f1['input_bundle_digest']}`。
S input bundle digest：`{s1['input_bundle_digest']}`。它们不同是记录的实验事实；没有重复生成直至相等。

**VERIFIED**：`{EXEC / 'stage_b_input_summary.json'}` 与 `{INPUTS / 'full_vs_singleton_matrix.csv'}`：20/20 base 联合 legacy digest 不同；14/20 center types、12/20 tiers、11/20 dt 不同；7/20 部署可行身份集合不同；80/80 原场景摘要及 5760/5760 stage-role 摘要不同。判据使用实际数组 legacy digest/字段；不是把含 context 名称的 provenance fingerprint 不同当作数组不同。

旧记录仍只有 `(33003,7313,C4)` 一个已观测跨方法外生配对异常，其他 239 组保存字段内部配对；但总体来源混合的范围为 239 F 与 961 S，不能把纠正任务缩成只处理一个组。F 当前类型分布 A6/B8/C6，S 为 A6/B9/C5；canonical 选择不依赖模型结果。
"""
reports = {}
reports["EXECUTION_SUMMARY.md"] = f"""# Execution Summary

{common}
## Actual stage ledger

| 阶段 | 实际状态 | 直接证据 |
|---|---|---|
| A verifier 合成测试 | PASS，最终全部 42 项；新目录内局部修订有记录 | `{EXEC / 'stage_a_attempt_05_results.json'}`；`STAGE_A_EXECUTED_AUDIT.md` |
| B input-only | PASS；实际四进程 F1/F2/S1/S2、历史映射与调度核验完成 | `{EXEC / 'stage_b_scientific_gate.json'}`；`{INPUTS / 'execution_receipt.json'}` |
| C 新执行器软件 | PASS，50/50 合成测试，0 fail/error/skip | `{RESULTS / 'stage_c_tests/attempt001/results.json'}` |
| C 模型环境冻结 | BLOCKED；退出码 1，未发布可执行 provenance manifest | `{RESULTS / 'PREPARE_FAILURE_OBSERVED.json'}` |
| C 初始化/最小五方法组 | NOT_EXECUTED，0/60 与 0/5 | 没有 initial_states/workers/raw/execution 产物 |
| D 纠正实验 | NOT_STARTED，0/1200 | `EXECUTION_STATUS.json` |
| E 统计/Bootstrap | NOT_EXECUTED | 没有新损失、CI、诊断统计 |

没有阶段间权限反复询问；本次停止适用研究者明示的“不可控依赖/无法证明科学公平性不得继续”规则。没有自动选择其他环境、安装包、用 stub 替代导入或删除未使用的原依赖。

## Blocker

{failure_refs}
## Preservation and Git

{original_refs}
## Deliveries and limitations

本目录六份 Markdown 是执行事实和停止报告，不能误当完成实验的论文主结果。`SOURCE_CONFIG_INPUT_EVIDENCE_MANIFEST.json` 绑定已完成输入、测试、冻结源与配置；明确 `is_runnable_execution_manifest=false`。输入实物保存在上面的独立 verification run，未覆盖 `results/p7_7/`。

未完整执行的 Stage E 代码草稿保留在 `{REPO / 'verification/paper3_canonical_inputs/replication_statistics_batch20_v1/statistics.py'}`，依赖尚未创建的 runtime_guard；没有测试或统计执行，不能标记 READY。真实模型环境与完整配对复核仍待研究者处置和授权。
"""
reports["INPUT_PARITY_AUDIT.md"] = f"""# Input Parity Audit

{common}
## Completed input-only facts

{stage_b_refs}
## New experiment parity gate

| 条件 | 判定 | 边界 |
|---|---|---|
| 同一 ordered batch20 输入可重复 | VERIFIED | 当前 source/NumPy 环境的 F1/F2 实测；不是完整历史环境证明 |
| singleton 对照可重复 | VERIFIED | S1/S2 实测，作为来源对照，不能代称原 batch 协议 |
| 一份 F1 输入供全部方法读取 | STATIC_VERIFIED/PENDING_MODEL_EXECUTION | loader 已实现与测试；未执行模型任务 |
| 60 个中心—种子初始参数参考 | NOT_VERIFIED | 0/60 warm-up |
| 240/240 五方法实际初始参数、约束、24-stage 输入配对 | NOT_VERIFIED | 0/240 新组，不能用旧 239 内部配对或软件测试替代 |
| 实际在线因果完整性 | NOT_VERIFIED_RUNTIME | timeline 的拒绝/许可路径通过合成测试；尚无真实 24-stage trace |
| 1200/1200 新轨迹 source/config/input receipts 绑定 | NOT_VERIFIED | 新 CSV/receipts 均为 0 |

**VERIFIED 静态行为**：{location('verification/paper3_canonical_inputs/replication_executor_batch20_v1/fixed_inputs.py','class FixedInputStore')} 只读 F1，保留原 array_digest/dtype/slicing；{location('verification/paper3_canonical_inputs/replication_executor_batch20_v1/executor_driver.py','def accepted_records')} 逐条核真实 F1 字段、初始证书与 receipts；`paired_groups` 核 24-stage 外生/初始/部署字段，不要求动作后 deployed state 相同。真实执行仍受未通过模型环境 gate 阻断。

## Evidence preservation

{original_refs}
"""
reports["EXPERIMENT_INTEGRITY_AUDIT.md"] = f"""# Experiment Integrity Audit

{common}
## Findings

| 分类 | 判定 | 实际行为和科学影响 |
|---|---|---|
| BLOCKER：当前模型依赖不完整 | VERIFIED | prepare 实际退出 1；不能进行初始化、公平性认证或完整复核 |
| BLOCKER：借用其他环境 ABI | VERIFIED/NOT_VERIFIED | 已定位 cp313 River/psutil，与 cp311 不等；其他路径不构成受控替代闭包 |
| MAJOR：原总体来源混合 | VERIFIED_R1 | 239 F/961 S；单组修复或文字修订不能恢复统一原人口的严格推断 |
| MAJOR：历史完整环境 | NOT_VERIFIED | 恢复历史源码和保存哈希对应不能代替历史 interpreter/package/native/GPU 环境 |
| 已完成：输入重复/映射/调度 | VERIFIED | Stage B 科学 gate PASS，未调用模型 |
| 已完成：新执行器软件 guard | VERIFIED_SYNTHETIC | 50/50，未认证真实运行的 R2/R3 |
| 原结果保存 | VERIFIED | 2535 protected 与 1201 ledger 全匹配，1200 CSV/1200 receipts |

{failure_refs}
## Frozen scientific logic

**STATIC_VERIFIED**：{location('verification/paper3_canonical_inputs/replication_executor_batch20_v1/science_adapter.py','def isolated_frozen_call')} 使用原 `run_one.__code__`，仅替换 `timeline_for_v2/scenario_hash_v2/initial_model` 的独立 globals；原函数、原 bank profiling、seed 规则、offline_labels 次序保留。新 RNG 留证不重设种子；原 MLP dropout 使用全局 Torch RNG，不能宣称模型结果在任何 worker order 下逐位相同。

**STATIC_VERIFIED**：{location('verification/paper3_canonical_inputs/replication_executor_batch20_v1/provenance.py','def install_generator_guard')} 阻断原 generation/refit/final entry；`install_write_guard/install_model_import_guard` 限定新输出与批准字节。它是 Python guard 加冻结 native 信任和原字节快照，不冒称 OS 全面沙箱。此次没有进入真实 model worker，因此没有真实 CUDA/device flags 或因果 trace 的 PASS。

历史 `audits/environment.json` 的 cudnn_deterministic=false 是 capture 阶段字段；{location('core/models.py','torch.backends.cudnn.deterministic')} 导入会设为 true。不能将二者直接写为本次模型运行改变了科学设置；本次没有模型导入，真实 runtime receipt 未产生。

## Acceptance checklist

仅软件与 input-only 已完成。1200 新轨迹、240 公平组、初始参数、完整 causal trace、实际 bank/A1 execution、joint Bootstrap 均未验证，故**不得报告科学完整性 PASS**。

{original_refs}
"""
reports["CORRECTED_FINAL_STATISTICS.md"] = f"""# Corrected Final Statistics

{common}
**NOT_COMPUTED — 没有新的主结果、均值差、Bootstrap、CI、场景统计或诊断统计。** 这不是零损失、零差异或不显著结果；所有新结果均未知。

| 预授权项目 | 本次实际状态 |
|---|---|
| 五方法 mean lifecycle service loss | NOT_COMPUTED |
| Proposed − B0/B1/B2/B8 观察均值差 | NOT_COMPUTED |
| 20中心联合配对 Bootstrap，4000，seed=2904，linear percentile95% | NOT_EXECUTED |
| C0/C1/C3/C4、LOO | NOT_COMPUTED |
| gate-open/RI/maintenance/retain/动作成本 | NOT_COMPUTED |
| missed-escalation 等原诊断 | NOT_COMPUTED |
| 实际决策运行时间、候选搜索 | 没有新模型观测；penalty 不等于完整实测计算成本 |

## Preserved analysis definition, not an execution claim

`{REPO / 'configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json'}` 的 `statistical_plan` 与 {location('scripts/run_p7_7_final.py','def _make_statistics')}：24-stage 服务均值→同中心 3 seeds×4 scenarios 的12轨迹平均→20中心平均。中心为重采样单位，不能把 240 组或 1200 轨迹当独立中心。

研究者本次要求所有五方法/四对比共享一份 4000×20 center index matrix；原实现为各方法/各 contrast 依次推进 RNG 的抽样数组。未来应明确披露此次联合抽样 convention，保持中心/4000/2904/linear95% 冻结要求；不可声称与历史抽样逐项完全相同。观察 point difference 必须直接由原样本中心均值相减，不能使用 Bootstrap replicate mean 代替。

未来只有在 1200/1200 + 240/240 和完整 source/config/input/initial/causal 证据全部通过后才允许统计；不能据结果方向筛除、重跑、调整 threshold 或 population。旧数值未重算也未替换，旧 CI 不能升级为此次 canonical population 的严格推断。

## Blocking evidence

{failure_refs}
"""
with (REPO/"results/p7_7/final_metrics_by_method.csv").open(encoding="utf-8-sig",newline="") as stream:
    saved_methods = list(csv.DictReader(stream))
historical_table = "| 方法 | 原保存 service mean（逐字字段） | 本次新 mean |\n|---|---:|---|\n"+"\n".join(
    f"| {row['method']} | {row['mean_lifecycle_service_loss']} | NOT_COMPUTED |" for row in saved_methods)
reports["ORIGINAL_VS_REPLICATION_COMPARISON.md"] = f"""# Original vs Replication Comparison

{common}
## Results boundary

以下旧数值从 `{REPO / 'results/p7_7/final_metrics_by_method.csv'}` 的 `mean_lifecycle_service_loss` 直接复制，没有重算原统计，没有计算新旧差：

{historical_table}

旧 Proposed gate-open 保存字段为 `{next(row['gate_open_rate'] for row in saved_methods if row['method']=='P7.7')}`；本次未知。旧表是原存量记录的历史描述，不能冒充统一 F 人口的纠正后结果、或严格 240 组公平性证明。

## Input population differences already observed without model outcomes

{stage_b_refs}
## Claims requiring revision

1. 原结果不能保留“所有20中心始终按同一 canonical population materialization”全称声明；旧 serial/parallel 分别 F/S，影响范围超过一组。
2. “所有五方法所有组共享初始状态/部署约束”不能无条件成立；保存外生字段与初始 hash 异常须如实披露；本次尚未完成新初始参数认证。
3. 不能通过文字修订把旧 Bootstrap 改称统一 full-batch population 的严格 paired evidence；完整纠正复核仍需执行，不选择有利组或替换局部结果。
4. 旧结果已被观察；未来完整复核只能称完整性纠正的独立 replication，不能称从未观察的 held-out evaluation。
5. 不改变原方法数学/阈值去迎合论文；Section3–4 的既有实现一致性审计意见继续保留，本次未解决其未决科学问题。无新结果可用来宣称 Proposed 改善、恶化、显著优势或等价性。

不能从已完成 input-only 字段比较确定新旧最终差的方向、大小或原因分解；此报告没有做性能导向协议选择。
"""
reports["SCIENTIFIC_FREEZE_DECISION.md"] = f"""# Scientific Freeze Decision

{common}
## Verdict

**不能冻结纠正性主实验结果，也不能提交为完成的新公平实验。** 软件与输入验证 PASS 不等于最终科学完整性 PASS；当前没有模型执行、初始化、1200新轨迹、240公平组或新统计。

## Verified and unresolved

VERIFIED：42 verifier tests；50 executor tests；F1/F2 与 S1/S2 repeatability；239旧F/961旧S 的 R1 映射；静态部署元数据与 fixed-input schedule/resume；原保护文件与 Git HEAD 保留。

NOT_VERIFIED：完整历史模型运行环境；受控当前 River/psutil 原生闭包；60 initial references；真实五方法参数公平性；全部240组 runtime/causal/input binding；完整复核性能、诊断与 Bootstrap。静态代码对象保留不能代替未执行的事实。

{failure_refs}
## Researcher decision required before any environment modification or resumed model execution

当前授权要求不可控依赖/科学冲突时停止。应先由研究者决定如何恢复或建立单独、可审计的模型环境，明确 interpreter、River0.23.0、psutil 版本、NumPy/pandas/Torch/native ABI 和依赖约束，以及它与已保存历史环境及冻结方法的关系。现有 River 的已发现 cp313/cp39 库不能直接塞进 cp311 path；不允许用伪模块、删导入、修改版本检查或自动改 pandas 来绕过。

若研究者授权新的受控环境处置，仍需重新冻结闭包/SHA、独立复核兼容性，保留所有失败与前任源码/manifest。已有 F1 输入是否可继续用必须按已冻结 array/dtype/hash 判据重核，不能为了 new outcome 改 protocol。随后重新通过真实 60 initial、预声明5方法 minimal、完整1200、240groups门槛后再统计；本次不会自动继续。

不得自动执行：安装或降级包、借用其他 site-packages、变更 Python/device/模型/方法、重训/refit、调 threshold/seeds/cost/bank、修改原1200文件、自动修复单组、Bootstrap/筛选新主结果、按结果优劣选择重跑、论文投稿定稿。

原 held-out 已被观察；即使未来所有完整性和统计门槛通过，也不授予“新未见数据”或自动论文科学冻结声明。

## Preservation

{original_refs}
"""
for name,text in reports.items(): publish(RESULTS/name,text.rstrip()+"\n")
draft = REPO/"verification/paper3_canonical_inputs/replication_statistics_batch20_v1/statistics.py"
if draft.exists():
    publish(draft.parent/"NOT_EXECUTED_BLOCKED.md" if draft.parent.is_relative_to(EXEC) else RESULTS/"STATISTICS_DRAFT_STATUS.md",
        "# Statistics Draft Status\n\nINCOMPLETE_NOT_EXECUTED. Stage C environment freeze failed; no Stage E execution.\n\n"
        f"Draft: `{draft}`\n\nSHA256: `{sha(draft)}`\n\nThe planned runtime_guard.py and synthetic tests were not delivered; do not invoke this draft.\n")
# Check again after report publication; reports are exclusively new files.
end_errors = [name for name,expected in snapshot.items() if sha(REPO/name) != expected]
if end_errors: raise RuntimeError("Original changed during delivery")
deliverables = {p.relative_to(RESULTS).as_posix():sha(p) for p in sorted(RESULTS.rglob("*")) if p.is_file()}
publish(RESULTS/"DELIVERY_MANIFEST.json",{"schema":"paper3-blocked-delivery-file-ledger-v1","status":"BLOCKED",
    "source_script":str(Path(__file__).resolve()),"source_script_sha256":sha(Path(__file__)),
    "files_sha256":deliverables,"self_excluded_from_hash_graph":True,
    "original_post_delivery_unchanged":True,"new_trajectories":0,"new_paired_groups_verified":0,
    "new_statistics_executed":False,"not_unseen_heldout":True,"completed_utc":datetime.now(timezone.utc).isoformat()})
print(json.dumps({"status":"BLOCKED","reports":list(reports),"trajectories":0,"paired_groups_verified":0,
    "protected_files_unchanged":2535,"original_ledger_matches":1201,"original_csv":1200,"original_receipts":1200,
    "Stage_A_tests":42,"Stage_C_tests":50,"Stage_B":"PASS","stop":"MODEL_ENVIRONMENT_INCOMPLETE"}))
