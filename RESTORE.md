# 恢复这份论文备份

## 方式一：Git

```powershell
git clone https://github.com/w924871681/three.git
cd three
git checkout paper3-full-data-env-20261010
python -B tools/verify_backup.py
```

`paper/` 包含整篇论文和可编辑 LaTeX；`figures/final/` 包含三张最终 PDF。`figures/corrected_batch20_final/` 包含 Fig.2/3 的600 dpi PNG、Matplotlib 源码、已验证绘图 CSV、图注和审计文件。

## 方式二：下载 Release 快照

打开 https://github.com/w924871681/three/releases/tag/paper3-full-data-env-20261010，下载 `PAPER3_COMPLETE_REPOSITORY_SNAPSHOT_20261010.zip` 及对应 `.sha256`。也可以使用：

```powershell
gh release download paper3-full-data-env-20261010 --repo w924871681/three --pattern 'PAPER3_COMPLETE_REPOSITORY_SNAPSHOT_20261010.zip*'
Get-FileHash -Algorithm SHA256 -LiteralPath .\PAPER3_COMPLETE_REPOSITORY_SNAPSHOT_20261010.zip
```

将输出与 sidecar 中的 SHA256 比较，然后解压到一个新目录，在其中运行 `python -B tools/verify_backup.py`。解压包本身不包含 `.git`，但包含同一提交的全部已保存有效文件。

## 重建图和论文

Fig.2/3 的可移植重绘入口：

```powershell
python -B figures/corrected_batch20_final/generate_paper3_figures.py --output NEW_FIGURE_OUTPUT --final
```

先按该目录 `FIGURE_DATA_PROVENANCE.md` 配置已记录的 Matplotlib/NumPy/Pillow 版本。输入默认读取脚本旁的冻结 `inputs/`；不需要模型实验或重算 Bootstrap。使用新输出目录，以保留归档原件。

论文编译入口为 `paper/latex/main.tex`，本地依赖均已包含，标准 TeX 发行版及 IEEEtran 等依赖要求见原包 `README_BUILD.md`。此次备份未重新编译论文。Fig.1 按作者要求仅保留 PDF。

完整科学证据保存为 `archives/PAPER3_FINAL_VERIFIED_EVIDENCE.zip`，可以另行解压。它包含正式报告、证书、统计、来源和历史证据。1200 份 raw CSV、完整 canonical 输入和两个完整安装环境现已在同一仓库的 [补充 Release](https://github.com/w924871681/three/releases/tag/paper3-full-data-env-20261010) 单独归档；见 [完整下载与恢复步骤](backup/full_data_environment/FULL_BACKUP_README.md)。原始 `paper3-20261010` 标签保留旧版本说明；当前 main 和新标签包含补充备份索引。

文件修改前保留该标签版本。后续论文修订应形成新的提交和标签，不覆盖本次历史归档。
