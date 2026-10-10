from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_PATH))

from core.common import ROOT, sha256_file


def main() -> None:
    required = [
        ROOT / "reports/P0_REPOSITORY_DISCOVERY.md",
        ROOT / "audits/REUSE_PROVENANCE.md",
        ROOT / "audits/reuse_hash_manifest.json",
        ROOT / "audits/P2_P3_SCIENTIFIC_AUDITS.json",
        ROOT / "audits/P3_DATA_AND_FIGURE_QA.md",
        ROOT / "results/p3/stage_records.csv",
        ROOT / "results/p3/candidate_records.csv",
        ROOT / "results/p3/p3_summary_by_condition_horizon.csv",
        ROOT / "results/p3/center_level_variability.csv",
        ROOT / "results/p3/p3_verdict.json",
        ROOT / "reports/P3_PHENOMENON_DIAGNOSTIC.md",
        ROOT / "figures/p3_stagewise_recoverability.pdf",
        ROOT / "figures/p3_stagewise_recoverability.png",
        ROOT / "figures/p3_stagewise_recoverability.svg",
        ROOT / "figures/p3_local_vs_reinstantiation_gap.pdf",
        ROOT / "figures/p3_local_vs_reinstantiation_gap.png",
        ROOT / "figures/p3_local_vs_reinstantiation_gap.svg",
    ]
    trajectory_files = sorted((ROOT / "results/p3/raw").glob("*.csv"))
    candidate_files = sorted((ROOT / "results/p3/candidates").glob("*.csv"))
    if len(trajectory_files) != 72 or len(candidate_files) != 72:
        raise SystemExit("expected exactly 72 raw and 72 candidate trajectory files")
    files = required + trajectory_files + candidate_files
    if any(not path.is_file() for path in files):
        raise SystemExit("required P3 artifact missing")
    manifest = {
        "schema": "dt-lifecycle-escalation/p3-artifact-manifest/v1",
        "p3_verdict": "FAIL",
        "raw_trajectory_files": len(trajectory_files),
        "candidate_trajectory_files": len(candidate_files),
        "heldout_materialized": False,
        "files": {
            path.relative_to(ROOT).as_posix(): {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        },
    }
    destination = ROOT / "audits/P3_ARTIFACT_MANIFEST.json"
    destination.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in manifest.items() if key != "files"}, indent=2))


if __name__ == "__main__":
    main()
