"""Publish versioned BLOCKED reports from saved, read-only review evidence.

No scientific or third-party imports. No installation, experiment or statistics.
Only the user-authorized root handoff is updated; its exact prior bytes are kept.
The six reports are updated in a new exclusive directory to retain old ledgers.
"""
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
HERE = Path(__file__).resolve().parent
OUT = REPO / "results/p7_7_integrity_replication_environment_review_20261009_v2"
PRIOR = REPO / "results/p7_7_integrity_replication_batch20_v1"
ROOT_HANDOFF = REPO / "PAPER3_FINAL_REPLICATION_HANDOFF.md"
PKG_HANDOFF = REPO / "handoffs/PAPER3_FINAL_REPLICATION_HANDOFF_20261009_BLOCKED_V1/PAPER3_FINAL_REPLICATION_HANDOFF.md"
REPORTS = ["EXECUTION_SUMMARY.md", "INPUT_PARITY_AUDIT.md", "EXPERIMENT_INTEGRITY_AUDIT.md", "CORRECTED_FINAL_STATISTICS.md", "ORIGINAL_VS_REPLICATION_COMPARISON.md", "SCIENTIFIC_FREEZE_DECISION.md"]

def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def load(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))

def text(p, content):
    with p.open("x", encoding="utf-8", newline="\n") as f:
        f.write(content)

def write_json(p, obj):
    text(p, json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n")

def git(*args):
    return subprocess.check_output(["git", "-C", str(REPO), *args], text=True, encoding="utf-8").strip()

def main():
    ev = load(HERE/"EVIDENCE.json")
    inv = load(HERE/"INSTALLED_ENVIRONMENT_INVENTORIES.json")
    assert ev["status"] == "BLOCKED"
    assert sha(HERE/"INSTALLED_ENVIRONMENT_INVENTORIES.json") == ev["environment_inventory"]["sha256"]
    assert all(value is False for value in ev["actions"].values())
    for k in ("original_preservation", "original_output_ledger", "prior_blocked_delivery_preservation", "historical_handoff_package_preservation", "stage_b_all_bound_files_preservation"):
        assert ev[k]["pass"], k
    assert ev["git_tracked_and_head_unchanged"]
    assert ev["new_trajectories_completed"] == ev["new_groups_certified"] == 0
    assert ev["original_csv_count"] == ev["original_receipt_count"] == 1200
    input_root = Path(ev["input_manifest"]["path"]).parent
    receipt = load(input_root/"execution_receipt.json")
    gate_path = REPO/"verification/paper3_canonical_inputs/execution_20261009/stage_b_scientific_gate.json"
    gate = load(gate_path)
    assert sha(input_root/"run_manifest.json") == ev["input_manifest"]["sha256"]
    assert sha(input_root/"execution_receipt.json") == ev["input_receipt"]["sha256"]
    assert sha(input_root/"execution_receipt.json") == gate["execution_receipt_sha256"] == "0cddc74b4fdfbb874a9142cccf271ed5368df684f44c38b5a86a73c04eb6405e"
    assert sha(input_root/"run_manifest.json") == receipt["run_manifest_sha256"]
    assert sha(input_root/"outputs_inventory.json") == receipt["outputs_inventory_sha256"]
    assert receipt["exit_code"] == 0 and receipt["status"] == "INPUT_ONLY_CHECKS_COMPLETED" and gate["execution_pass"]
    assert ev["fixed_F1_input_bundle_digest"] == "ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228"
    assert ROOT_HANDOFF.read_bytes() == PKG_HANDOFF.read_bytes(), "preserve unexpected user edits; do not overwrite"
    assert not OUT.exists(), "exclusive current review output already exists"
    stamp = datetime.now(timezone.utc).isoformat()
    OUT.mkdir()
    (OUT/"prior_version").mkdir()
    previous = ROOT_HANDOFF.read_bytes()
    with (OUT/"prior_version/PAPER3_FINAL_REPLICATION_HANDOFF.md").open("xb") as f:
        f.write(previous)
    for name in REPORTS:
        with (OUT/"prior_version"/name).open("xb") as f:
            f.write((PRIOR/name).read_bytes())

    inventory_path = HERE/"INSTALLED_ENVIRONMENT_INVENTORIES.json"
    evidence_path = HERE/"EVIDENCE.json"
    fingerprints = "\n".join(f"| {name} | `{item['inventory_fingerprint_sha256']}` |" for name,item in inv.items())
    evidence_table = f"""| 当前重新核验 | 数量/结果 | 证据范围 |
|---|---|---|
| 原始保护文件 | {ev['original_preservation']['checked_files']}，全部SHA一致 | 原StageA保护快照，含原源码/配置/模型/结果 |
| 原输出ledger | {ev['original_output_ledger']['checked_files']}，全部SHA一致 | 原1200CSV及保存manifest绑定 |
| 原CSV与receipt | {ev['original_csv_count']} / {ev['original_receipt_count']} | `.csv`与`.integrity.json`，原目录不变 |
| 保存的StageB绑定 | {ev['stage_b_all_bound_files_preservation']['checked_files']}，全部SHA一致 | 全部四context输入及run绑定文件，仅读取字节 |
| 旧阻断交付ledger | {ev['prior_blocked_delivery_preservation']['checked_files']}，全部SHA一致 | 原六报告/阻断manifest等保留 |
| 旧交接包ledger | {ev['historical_handoff_package_preservation']['checked_files']}，全部SHA一致 | 旧ZIP及包内历史版本保留 |
| 当前Py311精确`==`条目 | {ev['requirements_exact_pin_count']}/{ev['requirements_exact_pin_count']} metadata一致 | 不包含editable Git commit认证，不代表闭包可执行 |
"""
    common = f"""更新记录UTC：`{stamp}`。唯一目标仓库：`{REPO}`。

本轮状态 **BLOCKED**：新轨迹 **0/1200**，实际五方法配对认证 **0/240**，初始化 **0/60**，五方法最小检查 **0/5**。全部运行认证待执行，不是已失败240组。实际模型worker **0**；模型开始/结束时间 **NOT_STARTED / N/A**。本轮只取证和发布版本化报告，没有安装包、创建环境、运行项目导入/模型/生成器/优化器或新统计。

当前阻断与可核验证据见 `{evidence_path}` 和 `{OUT / 'MODEL_ENVIRONMENT_RECOVERY_REVIEW.md'}`。此前42/42、50/50和StageB PASS属于真实保存的前次结果；本轮未重跑测试，不把它们升级为新模型环境运行PASS。
"""
    review = f"""# Authorized Model Environment Recovery — BLOCKED Review

{common}
## 1. Stop decision and material scope

研究者授权了独立环境恢复和门槛通过后的连续实验，同时明确规定：**“如果冻结依赖版本无法确定，或者需要改变科学相关依赖，必须停止并报告，不能自行猜测。”** 本轮触发该停止条件；不是缺少环境安装权限。

材料覆盖：目标仓库中的冻结requirements、历史environment、P7/P7.7源码、Git全部历史相关依赖搜索、现有receipt/manifest、已注册和常见位置的本地环境及pip缓存。没有全盘断言不存在任何隐藏环境。前期审计、原论文/推荐稿不代替实现事实。无模型结果用于选择环境或决定继续。

## 2. Critical evidence and decisions

| 等级 | 完整路径、函数/字段、行号 | 实际证据及科学影响 |
|---|---|---|
| VERIFIED_PROTOCOL_PIN | `{REPO / 'scripts/run_p7.py'}`，`base_preflight`，80；`{REPO / 'configs/p7_baseline_grids.json'}`，`version`，31 | 协议指定River0.23.0；不能选择0.21.2或更新版替代。 |
| VERIFIED_HISTORICAL_RECORD | `{REPO / 'docs/P7_PROTOCOL_AND_EXECUTION_LOG.md'}`，24、35；`{REPO / 'audits/P7_PRE_OUTCOME_PROTOCOL_FREEZE.json'}`，8、10、12 | ADWIN2版本0.23.0及`--no-deps`安装记录由预结果SHA绑定；这是协议/安装叙述，不是最终全部1200运行环境闭包认证。 |
| NOT_VERIFIED_FINAL_RUNTIME | `{REPO / 'scripts/run_p7_7_final.py'}`，35 (`offline_labels` import)、440–456 (`_final_expected_receipt`) | 最终入口不调用上述River版本preflight；最终receipt绑定config/runner/core/output，不记录依赖版本。历史最终River实际版本仍未直接绑定。 |
| NOT_VERIFIED — B1 stop | `{REPO / 'configs/requirements_frozen.txt'}`，全文1–36；`{REPO / 'audits/environment.json'}`，2–11；`{REPO / 'scripts/run_p7_7_final.py'}`，25、852、854 | 无psutil版本pin；environment只记Python/Torch/CUDA等。资源API为`virtual_memory/cpu_count`，不直接进入模型loss/gate，但候选5.9.0或7.0.0不能冒称冻结历史版本。 |
| VERIFIED_DECLARED_CONFLICT — B2 stop | `C:\\Users\\92487\\anaconda3\\Lib\\site-packages\\river-0.23.0.dist-info\\METADATA`，18 (`Requires-Dist`)；`{REPO / 'configs/requirements_frozen.txt'}`，19 | River声明pandas>=2.2.3,<3.0.0，而冻结pandas3.0.5在区间之外。[River0.23.0官方源定义](https://raw.githubusercontent.com/online-ml/river/0.23.0/pyproject.toml)也指定pandas2系列。**只证实依赖声明冲突，不宣称已经证实import或模型数值运行失败。** |
| VERIFIED_ABI_TAG | `C:\\Users\\92487\\anaconda3\\Lib\\site-packages\\river-0.23.0.dist-info\\WHEEL`，4；同目录`psutil-5.9.0.dist-info\\WHEEL`，4 | 两者均cp313，不能混入本次cp311。其安装metadata不证明最终历史环境；本轮未复制或导入。 |
| VERIFIED_PARTIAL_ENVIRONMENT | `{inventory_path}`，`rcf-dti-py311.distributions/conda_records`；`{evidence_path}`，`requirements_exact_pins_compared` | 已检查现有Py311=3.11.15，35/35精确发行版pin匹配，缺River/psutil。版本一致不认证native载入/数值行为/CUDA/依赖闭包。 |
| VERIFIED_IMPORT_SIDE_EFFECT_RISK | `C:\\Users\\92487\\anaconda3\\envs\\rcf-dti-py311\\Lib\\site-packages\\complexity_constrained_few_shot_dt-1.1.9.dist-info\\direct_url.json`，1；requirements，2 | editable指向`D:/RCF_DTI_pre_submission`，不能证明要求Git commit来源。不得依靠site初始化让其他项目参与Paper3导入；本轮使用`-I -S -B`标准库取证，未导入editable代码。 |

River0.23.0是可确定的**协议要求**；历史最终实际版本另列NOT_VERIFIED，不把二者混同。requirements/environment Git写入为`4e215759b3e3e73afed434de70080188d8ab768d`（2026-09-14），早于P7 River预冻结`46ee80aa1473e2a74853165ead42e816aabe2ca8`（2026-09-16）。Git `-G`、已有日志/清单未找到精确psutil最终绑定，不把搜索未命中当作不存在任何外部证据。

## 3. Available environments and provenance

| 已检查环境 | Python | 关键依赖metadata | 结论 |
|---|---|---|---|
| `C:\\Users\\92487\\anaconda3\\envs\\rcf-dti-py311` | 3.11.15 | Torch2.5.1+cu121、NumPy2.4.6、pandas3.0.5、SciPy1.17.1、sklearn1.9.0；缺River/psutil | 科学版本pin部分匹配，完整模型闭包未通过 |
| `C:\\Users\\92487\\anaconda3` | 3.13.5 | River0.23.0/psutil5.9.0 cp313 | 不作为cp311恢复来源 |
| `C:\\Users\\92487\\anaconda3\\envs\\tf-gpu` | 3.9.23 | River0.21.2 cp39；psutil7.0.0 cp37-abi3 | River版本/NumPy/pandas声明不同；psutil的abi3标签不证明冻结版本，未实际载入 |
| `D:\\DT_UPDATE_WORKSPACE\\.conda\\jnca-cuda` | 3.12.13 | Torch2.10.0+cu126、NumPy2.5.2、SciPy1.18.0；缺River/psutil | Python和科学依赖不同，不采用 |

完整METADATA/WHEEL/INSTALLER/RECORD/direct_url、精确版本、相关`.pyd/.dll`SHA及conda记录见 `{inventory_path}`。解释器3.11.15的conda下载来源为`repo.anaconda.com/pkgs/main/win-64/python-3.11.15-hb00fc5c_1.conda`，记录文件位于该环境`conda-meta/python-3.11.15-hb00fc5c_1.json`。pip包缺少direct_url时，INSTALLER=pip仅证明安装工具，不证明下载索引或最终历史运行来源。未伪造安装来源。

| 环境 | 本轮metadata/interpreter/相关native inventory fingerprint |
|---|---|
{fingerprints}

这些fingerprint绑定**本轮只读盘点范围**，不是完整操作系统/GPU驱动复现或环境可运行证明。所有依赖恢复/安装动作均**未执行**，没有新环境或新安装源可报告。pip缓存只找到River0.23.0 cp313、River0.21.2 cp39、psutil7.0.0 abi3等候选；没有已定位cp311 River缓存，但这不证明公网没有合法wheel。本轮不根据可下载性选择版本。

## 4. Preserved input and artifacts

{evidence_table}

F1固定为`P7_7_ORIGINAL_BATCH20_CANDIDATE_V1`，来自成功RUN003，bundle digest `{ev['fixed_F1_input_bundle_digest']}`。Receipt byteSHA `{ev['input_receipt']['sha256']}`；核对成功exit0、保存run_manifest/output_inventory SHA、StageB scientific gate引用与全部绑定字节；未重新生成、选择或改变总体。

原模型/A1 checkpoint仅读取SHA，没有加载权重。冻结配置、source bank、A1 estimator/scaler、原代码/种子/零阈值/成本/候选库未改。完整原文件核验不认证真实初始化60参考、240部署与因果trace；这些仍NOT_VERIFIED。StageA42/42、StageC50/50保存测试结果仍保留，本轮未改变环境/执行器，无新增受影响测试可报告；恢复尚未完成，所有必需模块导入和checkpoint load验证NOT_EXECUTED。

Git实际根`{ev['git_start']['repo_root']}`；HEAD `{ev['git_start']['head']}`。查询均显式`git -C {REPO}`。既有tracked修改前后相同：

```text
{ev['git_start']['tracked_status']}
```

## 5. Additional executor limitations — static only, not patched

| 等级 | 实际路径/函数/行号 | 必要后续工作与边界 |
|---|---|---|
| VERIFIED | `{REPO / 'verification/paper3_canonical_inputs/replication_executor_batch20_v1/provenance.py'}`，`capture_model_environment`，236–258 | 目前锁定StageB interpreter路径/SHA、numpy_parent。未来独立环境需在新增执行器中分开绑定input-generation与model-runtime；不得改写旧StageB manifest或F1。 |
| VERIFIED | `{REPO / 'verification/paper3_canonical_inputs/replication_executor_batch20_v1/executor_driver.py'}`，`run`，329–333 | prepare只允许授权文件和stage_c_tests，现有旧阻断19项会被拒绝。采用新独占实验目录，或严谨的既存ledger核验恢复；不能删旧报告放行。 |
| VERIFIED | 同一`executor_driver.py`，`dispatch`，271–301 | phase request/cache/log固定名字与attempt，真实中断后需要独占新attempt并保留旧日志；不能覆盖或改变科学协议。 |
| VERIFIED | `{REPO / 'verification/paper3_canonical_inputs/replication_statistics_batch20_v1/statistics.py'}`，`run_statistics`，378；同目录文件清单 | 导入的`.runtime_guard`文件缺失，StageE草稿未就绪。须补新增guard和独立测试后才可统计，当前没有执行Bootstrap。 |

这些是新增实现限制，不是重新调参理由。本轮依据科学依赖停止条件停止后续实验工作，**没有修改执行器或统计草稿**；新代码仅为取证与报告发布脚本，其SHA由当前delivery manifest绑定。

## 6. Scientific consequences and next necessary evidence

新结果、四baseline观察差、CI、gate/RI/diagnostics均NOT_COMPUTED；新旧变化方向与数值未知。旧混合239F/961S及单组不匹配的限制不因本轮环境取证而消失。不能将缺失结果写为0、相等或不显著；旧统计继续以历史描述性证据保留。

恢复有两种需要研究者先解决的依据：取得可绑定实际最终执行的完整依赖/安装证据（特别psutil及River-pandas闭包）；或者研究者明确冻结一个**独立模型运行环境**及必要的非历史等价限制，具体指定psutil版本/来源，并对River声明冲突作明确科学处置。本轮授权没有提供这些决定，不能自行选版本或绕过声明。不能降级pandas/NumPy/Torch、升级River、删除imports、stub、混入cp313或忽略解析冲突后声称历史环境已恢复。

即使未来环境能运行，也须记录native/CUDA及来源差异，不能直接声称历史数值环境完全相同；保持已选F1，然后完成60初始状态认证、预声明minimal5、完整1200/240、center20/4000/seed2904联合Bootstrap及审计。旧held-out已经观察，仍只能称完整性纠正性独立复核。

## 7. Current deliverables

六份报告更新为独立V2，原V1报告/19项ledger、旧handoff目录和ZIP不变。根handoff更新为最新入口并保留其准确前一版本于本目录`prior_version/`。没有新统计CSV，已有CSV既不覆盖也不冒名。

- 新报告目录：`{OUT}`。
- 证据和环境fingerprint：`{HERE}`。
- 当前根交接入口：`{ROOT_HANDOFF}`。
- 当前source/config/input/output绑定：本目录`CURRENT_DELIVERY_MANIFEST.json`及SHA sidecar；manifest排除自身及sidecar，避免循环hash。

最终：**BLOCKED；0/1200；0/240；0个模型worker；原始与F1完整保留；没有新的实验结果或性能归因。**
"""
    text(OUT/"MODEL_ENVIRONMENT_RECOVERY_REVIEW.md", review)
    update_bodies = {
        "EXECUTION_SUMMARY.md": "本轮实际完成受控恢复的只读取证阶段，并依据B1/B2停止。没有创建环境、安装依赖、运行模块导入或启动prepare/initial/minimal/full。环境审查时间只表示取证开始/结束，不是模型实验时间。\n\n" + evidence_table,
        "INPUT_PARITY_AUDIT.md": f"保存F1 bundle `{ev['fixed_F1_input_bundle_digest']}` 不变；成功receipt、run_manifest、outputs_inventory互相绑定且全部{ev['stage_b_all_bound_files_preservation']['checked_files']}输入run绑定文件字节一致。这里只重核保存材料，没有重新生成总体。实际60初始/240模型共同输入与部署认证仍待执行；旧239份F记录/961份S记录来源映射及239/240组内部配对，不认证新实验。",
        "EXPERIMENT_INTEGRITY_AUDIT.md": "科学完整性PASS **不能报告**。原始2535文件、1201输出ledger、1200CSV/1200receipts保留；旧blocked交付和ZIP原样保留。现有依赖闭包不完整，psutil冻结来源未确定，River声明与pandas冻结版本冲突。数值运行、初始状态和在线因果runtime认证未执行。\n\n" + evidence_table,
        "CORRECTED_FINAL_STATISTICS.md": "**NOT_EXECUTED / NOT_COMPUTED**。没有任何新的method/scenario均值、观察差、Bootstrap4000/seed2904区间、gate/RI/actions或missed-escalation结果。没有生成统计CSV，旧统计CSV保留，不能改名为corrected。未知不能替换为0/相等/不显著。StageE草稿缺runtime_guard，也未视为就绪。",
        "ORIGINAL_VS_REPLICATION_COMPARISON.md": "旧实验1200存量记录仍混合239F/961S，且33003/7313/C4存在跨方法不匹配；新轨迹0，无法计算变化或归因。此前root handoff和本报告历史版本保留完整旧保存统计，未重新聚合或选择性删除。本轮依赖取证与F1哈希保存不能提供性能变化证据。",
        "SCIENTIFIC_FREEZE_DECISION.md": "**BLOCKED，不能科学冻结纠正性模型实验或新统计结论。** 真实保存A42/B输入/C50通过仍成立；新模型环境、60初始、minimal5、1200完成/240公平配对和统计尚未验证。本轮停止依据是研究者规定的未知冻结依赖/科学依赖冲突条件，不是缺乏一般安装权限。需先取得依赖证据或明确独立runtime冻结处置，然后完成必要新执行器修订/测试及已授权门槛。原方法和已保存F1不可调整，结果方向不能用于决定方案。"
    }
    for name in REPORTS:
        archival = (PRIOR/name).read_text(encoding="utf-8")
        text(OUT/name, f"# {name[:-3]} — Authorized environment review V2\n\n{common}\n## Current update\n\n{update_bodies[name]}\n\n详见 `{OUT / 'MODEL_ENVIRONMENT_RECOVERY_REVIEW.md'}`。\n\n---\n\n## Preserved prior V1 report (historical version)\n\n下文原样保留前次报告，时间、路径和统计标签均属于该历史版本。当前结论以上方V2及当前来源清单为准。\n\n{archival}")
    status = {"schema": "paper3-environment-review-execution-status-v2", "status": "BLOCKED", "updated_utc": stamp, "environment_review_started_utc": ev["review_started_utc"], "environment_review_finished_utc": ev["review_finished_utc"], "model_experiment_started_utc": None, "model_experiment_finished_utc": None, "new_trajectories_completed": 0, "paired_groups_verified": 0, "initial_states_verified": 0, "minimal_five_method_completed": 0, "model_workers": 0, "new_statistics_performed": False, "source_of_counts": str(evidence_path), "environment_restored": False, "executor_modified": False, "reasons": ev["blockers"]}
    write_json(OUT/"EXECUTION_STATUS.json", status)
    copy_evidence = {"evidence": {"path": str(evidence_path), "sha256": sha(evidence_path)}, "environment_inventory": {"path": str(inventory_path), "sha256": sha(inventory_path)}, "source_bindings": ev["source_bindings"], "stage_b_input_manifest": ev["input_manifest"], "stage_b_receipt": ev["input_receipt"], "fixed_F1_input_bundle_digest": ev["fixed_F1_input_bundle_digest"], "no_runnable_model_environment_published": True, "is_runnable_execution_manifest": False, "previous_delivery": str(PRIOR/"DELIVERY_MANIFEST.json"), "previous_handoff_zip": ev["historical_handoff_zip"]}
    write_json(OUT/"SOURCE_CONFIG_INPUT_EVIDENCE_MANIFEST.json", copy_evidence)
    table = "\n".join(f"| {n} | `{OUT/n}` |" for n in REPORTS)
    current_section = f"""## 0. Latest authorized environment recovery review — V2

当前更新UTC：`{stamp}`；环境取证UTC：`{ev['review_started_utc']}`至`{ev['review_finished_utc']}`。这些都不是模型实验时间。**BLOCKED：新轨迹0/1200，新五方法认证0/240，初始化0/60，minimal0/5，模型worker0。** 本轮未安装任何依赖或创建环境；未运行项目导入、模型加载、warm-up、最终实验或Bootstrap。此前A42/B/C50保存PASS没有升级为新的runtime PASS。

停止原因：psutil精确冻结/最终运行版本与来源仍**NOT_VERIFIED**；River协议pin0.23.0已确认，但其METADATA声明pandas>=2.2.3,<3.0.0，与冻结pandas3.0.5有**VERIFIED声明冲突**。[River官方0.23.0源定义](https://raw.githubusercontent.com/online-ml/river/0.23.0/pyproject.toml)与本地metadata相符。尚未证实该组合实际runtime一定失败，亦未恢复完整历史环境。按本次明确的“冻结依赖版本无法确定…必须停止”条件，未猜测版本、忽略冲突或改变科学依赖。

原2535文件、原1201ledger、原1200CSV/1200receipts与保存的{ev['stage_b_all_bound_files_preservation']['checked_files']}StageB绑定均重新验证字节一致，F1仍 `{ev['fixed_F1_input_bundle_digest']}`。旧V1报告/ledger和交接ZIP原样保留。当前六报告更新在独立V2目录，避免覆盖历史来源绑定；没有新统计CSV，新旧均值差/CI均NOT_COMPUTED。

| Current report | Full path |
|---|---|
{table}

详细受控环境审查：`{OUT / 'MODEL_ENVIRONMENT_RECOVERY_REVIEW.md'}`。精确版本、来源及binary/metadata指纹：`{inventory_path}`。原文件/F1/旧交付/Git证明：`{evidence_path}`。当前交付与source/config/input SHA：`{OUT / 'CURRENT_DELIVERY_MANIFEST.json'}`及同名SHA sidecar。实际原始数据和实验目录沿用下方历史索引；本轮没有新的模型执行目录或原始轨迹。

新增执行器的独立环境绑定、已存在blocked目录接受/新独占目录、phase独占恢复和StageE缺失runtime_guard问题仅完成静态识别，未修改代码。需要先补依赖来源/冻结处置，再做新增实现的必要修订和测试；不能改旧StageB manifest、原方法或已选F1来通过检查。

下一步必要依据：历史完整依赖证据，或研究者明确冻结独立model-runtime及具体psutil版本/来源、River声明冲突处置与非历史等价限制。本轮不是因常规环境安装权限不足而停止。论文暂无纠正性实验结果可替换旧主统计；旧held-out已观察的限制继续成立。

根handoff的准确前一版本保存在 `{OUT / 'prior_version/PAPER3_FINAL_REPLICATION_HANDOFF.md'}`，旧ZIP未重打包。下方原V1交接正文及其数字/路径按历史版本原样保留，**最新状态和六报告路径以上方V2为准**。

---

"""
    new_handoff = "# Paper 3 Final Replication Handoff\n\n" + current_section + "## Archived V1 handoff body\n\n" + previous.decode("utf-8")
    staging = HERE/"PAPER3_FINAL_REPLICATION_HANDOFF.updated.tmp"
    text(staging, new_handoff)
    assert ROOT_HANDOFF.read_bytes() == previous
    os.replace(staging, ROOT_HANDOFF)
    # Final preservation; reports are intentionally outside every old ledger.
    baseline = load(REPO/"verification/paper3_canonical_inputs/execution_20261009/original_protected_start_sha256.json")
    assert all(sha(REPO/n) == digest for n,digest in baseline.items())
    old_delivery = load(PRIOR/"DELIVERY_MANIFEST.json")
    assert all(sha(PRIOR/n) == digest for n,digest in old_delivery["files_sha256"].items())
    assert git("rev-parse", "HEAD") == ev["git_start"]["head"]
    assert git("status", "--porcelain=v1", "-uno") == ev["git_start"]["tracked_status"]
    final = {"original_protected_files": len(baseline), "all_original_bytes_unchanged": True, "prior_delivery_files": len(old_delivery["files_sha256"]), "prior_delivery_unchanged": True, "old_handoff_zip_sha256": sha(Path(ev["historical_handoff_zip"]["path"])), "old_zip_unchanged": sha(Path(ev["historical_handoff_zip"]["path"])) == ev["historical_handoff_zip"]["sha256"], "git_head_unchanged": True, "tracked_status_unchanged": True, "updated_root_handoff": str(ROOT_HANDOFF), "updated_root_sha256": sha(ROOT_HANDOFF), "preserved_prior_root_sha256": sha(OUT/"prior_version/PAPER3_FINAL_REPLICATION_HANDOFF.md"), "no_scientific_execution": True, "time_utc": datetime.now(timezone.utc).isoformat()}
    assert final["old_zip_unchanged"]
    write_json(OUT/"FINAL_PRESERVATION_CHECK.json", final)
    files = [p for p in OUT.rglob("*") if p.is_file()] + [p for p in HERE.iterdir() if p.is_file()] + [ROOT_HANDOFF]
    manifest = {"schema": "paper3-current-environment-blocked-delivery-v2", "status": "BLOCKED", "completed_utc": datetime.now(timezone.utc).isoformat(), "new_trajectories": 0, "new_paired_groups_verified": 0, "new_statistics_executed": False, "file_bindings_sha256": {str(p):sha(p) for p in sorted(set(files))}, "self_excluded": [str(OUT/"CURRENT_DELIVERY_MANIFEST.json"), str(OUT/"CURRENT_DELIVERY_MANIFEST.json.sha256")], "previous_immutable_delivery_manifest": str(PRIOR/"DELIVERY_MANIFEST.json"), "source_config_input_manifest": str(OUT/"SOURCE_CONFIG_INPUT_EVIDENCE_MANIFEST.json"), "historical_environment_reproduced": False, "not_unseen_heldout": True}
    write_json(OUT/"CURRENT_DELIVERY_MANIFEST.json", manifest)
    text(OUT/"CURRENT_DELIVERY_MANIFEST.json.sha256", sha(OUT/"CURRENT_DELIVERY_MANIFEST.json") + "  CURRENT_DELIVERY_MANIFEST.json\n")
    print(json.dumps({"status":"BLOCKED", "reports":str(OUT), "root_handoff":str(ROOT_HANDOFF), "manifest_sha256":sha(OUT/"CURRENT_DELIVERY_MANIFEST.json"), "new_trajectories":0, "new_groups":0, "preservation":final}, ensure_ascii=False))

if __name__ == "__main__":
    main()
