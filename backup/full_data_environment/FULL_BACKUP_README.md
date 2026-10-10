# Paper 3 完整数据与环境补充备份

本版补齐作者明确要求的本地资料，原 `paper3-20261010` 论文、三张图、LaTeX、代码、统计与科学证据版本保持不变。Fig.1 按作者要求仅保留 PDF。

| 分组 | 文件数 | 未压缩字节 |
|---|---:|---:|
| 1200 原始轨迹 CSV + 1200 receipt | 2400 | 51,284,277 |
| 完整 F1 输入、60 初始参考及来源文件 | 619 | 366,539,367 |
| 完整受控模型 venv | 24568 | 4,937,988,652 |
| 完整基础 Conda 环境 | 37335 | 5,299,923,657 |

共 64,922 文件，10,655,735,953 原始字节；ZIP 分卷总计 3,121,304,009 字节。附件包含原 `.zip.NNN` 分卷及较小的 `.zip.NNN.net64.MMM` 传输片段，均不能单独解压。恢复脚本严格按照 manifest 中的有序清单拼接，整体 ZIP 字节和 SHA256 保持不变；请勿按文件名自行排序拼接。`*_FILES.json` 记录每一个文件的实际原路径、归档路径、大小及 SHA256；`FULL_BACKUP_MANIFEST.json` 绑定全部索引、ZIP 与分卷 SHA256。

基础环境中 12,153 个文件与受控环境内容完全相同，采用 SHA256 验证后的内容引用，避免重复传输 4,589,614,295 字节。清单保留全部原文件，恢复脚本会复制为两个独立的完整目录；仅选择基础环境时也会自动验证所需的受控环境分卷。

下载本版所有附件到同一目录，用 Python 3.10+（仅标准库）运行：

```powershell
gh release download paper3-full-data-env-20261010 --repo w924871681/three --dir paper3_full_assets
python -I -S -B paper3_full_assets/restore_full_backup.py --manifest paper3_full_assets/FULL_BACKUP_MANIFEST.json --assets paper3_full_assets --output paper3_restored --verify-only
python -I -S -B paper3_full_assets/restore_full_backup.py --manifest paper3_full_assets/FULL_BACKUP_MANIFEST.json --assets paper3_full_assets --output paper3_restored
```

输出必须为不存在或空目录；脚本不覆盖已有文件，不执行恢复出的程序。仅需要数据时加 `--groups raw canonical`。恢复环境请先阅读 `ENVIRONMENT_RESTORE_NOTES.md`，Windows/NVIDIA 驱动是外部前提，历史数值等价性仍为 NOT_VERIFIED。

这些是原文件备份，没有重新训练、重新生成输入、重算 Bootstrap 或修改论文。原始轨迹及 canonical 冻结哈希在打包时核对；正式科学证据继续引用原已验证归档。

`PAPER3_BACKUP_AUDIT_20261010.zip` 保存完整盘点依据、各组打包收据及归档源码。发布前另用恢复程序只读解压核验每个归档成员，并逐一核对 GitHub 返回的附件 SHA256。
