# Paper 3 已安装环境恢复说明

本快照保存受控模型环境和它实际依赖的指定 conda 基础环境，共 **61,903 个文件、10,237,912,309 字节（9.534799 GiB）**。它覆盖两个目录内全部实际文件，包括 `.pyc`、`.dist-info`、`RECORD`、`conda-meta`、许可证/NOTICE、脚本、头文件、数据和原生 DLL；未按“运行必需文件”删减。

| 目录 | 原始绝对路径 | 归档目录 | 文件数 | 字节数 |
|---|---|---|---:|---:|
| 受控 venv | `D:\dt-talk\DT_LIFECYCLE_ESCALATION\verification\paper3_canonical_inputs\model_env_recovery_v1_20261009\P7_7_REPLICATION_MODEL_ENV_V1` | `environments/P7_7_REPLICATION_MODEL_ENV_V1` | 24,568 | 4,937,988,652 |
| conda 基础环境 | `C:\Users\92487\anaconda3\envs\rcf-dti-py311` | `environments/rcf-dti-py311` | 37,335 | 5,299,923,657 |

受控 venv 含 852 个 bytecode 文件、408 个安装元数据文件和 99 个许可证/声明文件；基础环境相应为 11,452、385 和 139 个。两目录共记录 4,832 个子目录，未发现 reparse point、缺失的预期文件、遍历错误、预期哈希冲突或有效预期尺寸不符。

恢复目标为 **Windows AMD64 + Anaconda CPython 3.11.15**。`pyvenv.cfg`、console launcher、conda 元数据和实验记录包含原始绝对前缀；要保持原样恢复，应将两个目录放回表中对应路径，并先校验归档及逐文件 SHA256。只恢复 venv 会缺少基础解释器、stdlib 和部分 native dependency。若必须迁移路径，应另行评审 relocation 修改；修改后的副本不再是原始字节快照。

受控启动策略是 **`-I -S -B`**：由已审定入口显式加入受控 venv 的 `Lib\site-packages`，保持 `include-system-site-packages=false`，不执行 `.pth`。不要用普通激活后的 Python 启动替代这套策略。基础环境内的 `complexity_constrained_few_shot_dt 1.1.9` editable hook 指向 `D:\RCF_DTI_pre_submission`；它在受控启动中不被处理，该外部项目不属于本环境依赖快照。

历史 native map 另有 **49 个 Windows/NVIDIA 系统 DLL 引用**，列在 `ENVIRONMENT_SUMMARY.json` 的 `externalNativeReferences` 中。恢复机器须另外具备相容的 Windows 系统组件和 NVIDIA 驱动；快照不包含 Windows 系统目录或驱动安装包。已保存的兼容性证据记录 Torch `2.5.1+cu121`、CUDA `12.1`、NVIDIA GeForce RTX 3060 Laptop GPU；此次整理没有再次运行 import、模型、训练或兼容性测试。

`ENVIRONMENT_INVENTORY.json` 给出完整逐文件目录、大小和可直接取得的既有预期 SHA256（40,656 个文件）。这类预期值不是此次对所有文件重新哈希的证明；应以打包阶段产生的校验清单核对实际备份。Conda `noarch=python` 路径已按 Windows 安装位置映射；使用 `sha256_in_prefix` 作为安装文件预期值，发生 prefix replacement 时不把包内原始尺寸冒充安装尺寸。

历史 GPU-driver binary identity、历史环境完全等价及完全相同的数值结果仍为 **NOT_VERIFIED**。这是两个指定已安装环境的文件快照，不是整机/操作系统镜像；不覆盖其他 conda 环境、Anaconda 全局包缓存、其他项目、注册表、ACL 或 hardlink identity。
