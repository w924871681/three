# 恢复这份论文备份

## 方式一：Git

```powershell
git clone https://github.com/w924871681/three.git
cd three
git checkout paper3-20261010
python -B tools/verify_backup.py
```

`paper/` 包含整篇论文和可编辑 LaTeX；`figures/final/` 包含三张最终 PDF。`figures/corrected_batch20_final/` 包含 Fig.2/3 的600 dpi PNG、Matplotlib 源码、已验证绘图 CSV、图注和审计文件。

## 方式二：下载 Release 快照

打开 https://github.com/w924871681/three/releases/tag/paper3-20261010，下载 `PAPER3_REPOSITORY_BACKUP_20261010.zip` 及对应 `.sha256`。也可以使用：

```powershell
gh release download paper3-20261010 --repo w924871681/three --pattern 'PAPER3_REPOSITORY_BACKUP_20261010.zip*'
Get-FileHash -Algorithm SHA256 -LiteralPath .\PAPER3_REPOSITORY_BACKUP_20261010.zip
```

将输出与 sidecar 中的 SHA256 比较，然后解压到一个新目录，在其中运行 `python -B tools/verify_backup.py`。解压包本身不包含 `.git`，但包含同一提交的全部已保存有效文件。

## 重建图和论文

Fig.2/3 的可移植重绘入口：

```powershell
python -B figures/corrected_batch20_final/generate_paper3_figures.py --output NEW_FIGURE_OUTPUT --final
```

先按该目录 `FIGURE_DATA_PROVENANCE.md` 配置已记录的 Matplotlib/NumPy/Pillow 版本。输入默认读取脚本旁的冻结 `inputs/`；不需要模型实验或重算 Bootstrap。使用新输出目录，以保留归档原件。

论文编译入口为 `paper/latex/main.tex`，本地依赖均已包含，标准 TeX 发行版及 IEEEtran 等依赖要求见原包 `README_BUILD.md`。此次备份未重新编译论文。Fig.1 仅保留现有 PDF，未找到编辑源文件。

完整科学证据保存为 `archives/PAPER3_FINAL_VERIFIED_EVIDENCE.zip`，可以另行解压。它包含正式报告、证书、统计、来源和历史证据；大型 raw CSV 与已安装环境未包含其中，只有其实际路径与哈希索引。恢复图表和阅读论文无需这些大型文件，重建完整实验环境则需要另外保存的实验数据和依赖。

文件修改前保留该标签版本。后续论文修订应形成新的提交和标签，不覆盖本次历史归档。
