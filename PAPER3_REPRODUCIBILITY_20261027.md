# Paper 3: environment, restoration and reproducibility status

This guide supplements the archived 2026-10-10 release. The environment and input data are already published as assets in [paper3-full-data-env-20261010](https://github.com/w924871681/three/releases/tag/paper3-full-data-env-20261010). `git clone` alone does not download these large assets.

## Scope and verified results

* The release contains both the controlled Windows CPython 3.11.15 model environment (24,568 files) and the base Conda environment (37,335 files), as well as the archived raw trajectories and canonical inputs. The environment archives are backups of the independent corrective replication runtime, **not proof of the original historical runtime's numerical equivalence**.
* On 2026-10-27, the existing base interpreter and controlled site-packages were used with Python `-I -S -B` to execute `figures/corrected_batch20_final/generate_paper3_figures.py --final` from the bundled saved input tables. The two PDFs and two PNGs matched the archived SHA-256 values exactly. This check redraws saved statistics; it does not rerun models or resample Bootstrap.
* The experiment sources retain original absolute paths and execution guards. A fresh-machine, end-to-end model rerun, relocation of these environments, and full numerical agreement have **not** been verified. This archive is not a tested one-command experiment installer. Do not interpret a successful restore or figure redraw as a model-reproduction result.
* Fig.1 is the original provided PDF; no Fig.1 source generator is included. Four tables are in the LaTeX source; corrected statistics are in `evidence/statistics/`.

## Download and verify the complete backup

Use GitHub CLI and a separate Python 3.10+ installation. Downloading all assets requires about 3.2 GB; extraction requires over 10 GB plus space for temporary joined ZIPs. The output directory must not exist or must be empty. Do not concatenate split files by hand.

```powershell
gh release download paper3-full-data-env-20261010 --repo w924871681/three --dir paper3_full_assets
python -I -S -B paper3_full_assets/restore_full_backup.py --manifest paper3_full_assets/FULL_BACKUP_MANIFEST.json --assets paper3_full_assets --output paper3_restored --verify-only
python -I -S -B paper3_full_assets/restore_full_backup.py --manifest paper3_full_assets/FULL_BACKUP_MANIFEST.json --assets paper3_full_assets --output paper3_restored
```

See [complete backup instructions](backup/full_data_environment/FULL_BACKUP_README.md), [environment restore constraints](backup/full_data_environment/ENVIRONMENT_RESTORE_NOTES.md), and [source scope and limitations](backup/CODE_SCOPE.json). Restoration validates archives and member hashes, but does not run the environment. A sidecar hash checks corruption, not publisher identity. The saved environments depend on Windows AMD64, the base interpreter, native DLLs, original prefixes and compatible NVIDIA drivers; neither the OS nor drivers are included. Migration needs separate validation; do not overwrite existing environments.

## Redraw experiment figures

The figure script and frozen input tables are in `figures/corrected_batch20_final/`. The recorded drawing environment used CPython 3.11.15, Matplotlib 3.11.1, NumPy 2.4.6 and Pillow 12.3.0, with the controlled site-packages and the `-I -S -B` startup policy; see [figure provenance](figures/corrected_batch20_final/FIGURE_DATA_PROVENANCE.md). Run the script using a compatible environment and a new output directory:

```powershell
python -B figures/corrected_batch20_final/generate_paper3_figures.py --output NEW_EMPTY_OUTPUT_DIRECTORY --final
```

The command requires the listed plotting dependencies. Merely installing those three top-level packages is not a validated recreation of the full archived environment; see the provenance and environment notes. Archive hashes for reference:

```
88ac94d8134d563265d87d2fd82f923d68f9b02d3a9c0c38f065b388d8e25943  Fig2_Paired_Service_Loss.pdf
5a999d192147b9c5055ab6a550e3a259937978bf659edab2379938b3b99a4b69  Fig2_Paired_Service_Loss.png
a110b111ab9ac6086fc24f148d4adab853ce9723b09f2cf63a34fff347471ef4  Fig3_Selective_Search.pdf
033060584bcf13fd4aad823091e739d25951e64e0a350af88c0cab61f3f50099  Fig3_Selective_Search.png
```

Different versions or fonts can change output bytes. Check `PLOT_DATA.json` and the scientific provenance in addition to images. The experiment uses previously observed inputs and must not be represented as a newly unseen holdout.
