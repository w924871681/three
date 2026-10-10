# Paper 3 — Bounded Maintenance Recoverability

**Bounded Maintenance Recoverability for Selective Lifecycle Escalation of Digital-Twin Models**

第三篇论文及其图表、LaTeX、绘图源码、实验/校验源码和正式纠正性证据的保存仓库。此版本保存作者于 **2026-10-10** 提供的完整论文与三张图，以及已验证的 canonical F1 **batch20 integrity-correction replication** 材料。

## 论文和三张正式图

- [完整论文 PDF](paper/PAPER3_FINAL_THREE_FIGURES_20261010.pdf)
- [LaTeX 主文件](paper/latex/main.tex) · [原包编译说明](paper/latex/README_BUILD.md)
- [Fig.1 — Selective lifecycle escalation](figures/final/Fig1_Selective_Lifecycle_Escalation.pdf)
- [Fig.2 — Paired service-loss comparison](figures/final/Fig2_Paired_Service_Loss.pdf)
- [Fig.3 — Selective search and action behavior](figures/final/Fig3_Selective_Search.pdf)
- [作者提供的原始 LaTeX ZIP](archives/PAPER3_FINAL_THREE_FIGURES_LATEX_20261010.zip)

论文 PDF、LaTeX 原包及三张 PDF 图均按原字节保存；未在上传过程中修改正文或重新编译。包内三张图和论文 PDF 与作者提供的独立文件逐一一致。论文中的表格保存在 LaTeX 内，对应的正式统计 CSV 见 `evidence/statistics/`。

## 绘图代码与实验资料

- [Fig.2/3 Matplotlib 绘图脚本](figures/corrected_batch20_final/generate_paper3_figures.py)
- [绘图输入、图注、来源与科学审计](figures/corrected_batch20_final/FIGURE_DATA_PROVENANCE.md)
- [绘图包清单](figures/corrected_batch20_final/FIGURE_MANIFEST.json)
- [实验、统计、动态调度和验证代码快照](code/)
- [源码范围与冻结哈希核对](backup/CODE_SCOPE.json)
- [正式科学证据交接](evidence/PAPER3_FINAL_VERIFIED_HANDOFF.md)
- [最终统计验证](evidence/FINAL_STATISTICS_VERIFICATION.md)
- [正式统计 CSV / Bootstrap 保存文件](evidence/statistics/)
- [完整已验证科学证据原 ZIP](archives/PAPER3_FINAL_VERIFIED_EVIDENCE.zip)

Fig.2/3 的 PDF、600 dpi PNG、生成脚本和所需已保存 CSV 一并保存。Fig.1 按作者要求仅归档正式 PDF。

`code/` 保留原仓库相对目录，包含当前关联源码与冻结配置/小型模型文件。它是源码保存快照，含历史开发入口；正式数值依据始终是上面的纠正性证据包。不要将旧脚本默认指向的历史结果当成正式 batch20 结果。仅恢复论文/图表不需要运行模型实验。

## 科学与备份范围

正式纠正性证据报告 1200/1200 轨迹、240/240 配对方法组和60/60初始参考。Proposed 相对 B8 的观察差值约为 `+0.0000280169`，95%区间跨零，不支持优势、等价或非劣效结论。搜索更新工作量与端到端实测计算成本是不同指标。此次输入此前已观察，不能称为全新未见 held-out；历史环境数值等价性仍为 `NOT_VERIFIED`。

这次上传保存现有论文版本与证据，不代表独立完成全文投稿级科学审校。

**完整数据与环境已另存于同一仓库的 [补充 Release](https://github.com/w924871681/three/releases/tag/paper3-full-data-env-20261010)**：1200 份 raw CSV 及1200份 receipt、完整 canonical F1 数组、60 初始参考，以及受控 venv 和基础 Conda 两个完整安装目录（包括目录内缓存、元数据、许可证及原生库）。大型二进制采用 Release 分卷保存，因此只执行 `git clone` 不会自动下载它们。

查看 [完整备份清单与恢复方法](backup/full_data_environment/FULL_BACKUP_README.md)、[分卷与索引 SHA256 清单](backup/full_data_environment/FULL_BACKUP_MANIFEST.json) 和 [环境恢复约束](backup/full_data_environment/ENVIRONMENT_RESTORE_NOTES.md)。逐文件实际路径和 SHA256 位于 Release 的 `*_FILES.json`。Windows 系统及 NVIDIA 驱动不属于 Python 环境目录快照。

## 恢复与完整性

当前完整备份索引由版本标签 `paper3-full-data-env-20261010` 固定；原 `paper3-20261010` 标签和 Release 保留。新 Release 另提供 `PAPER3_COMPLETE_REPOSITORY_SNAPSHOT_20261010.zip` 及 SHA256，包含论文、图、代码、证据和最新恢复工具；大型数据与环境由同一 Release 的分卷提供。

```powershell
git clone https://github.com/w924871681/three.git
cd three
git checkout paper3-full-data-env-20261010
python -B tools/verify_backup.py
```

校验脚本只检查 `BACKUP_MANIFEST.json` 中的文件大小与 SHA256，不运行训练、实验或统计。[恢复说明](RESTORE.md) 提供免 Git 的下载方式。

本仓库未额外指定开源许可证；保留各文件已有的来源与权利声明。
