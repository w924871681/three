from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MSA = Path(r"D:\dt-talk\repository")
RAVM = Path(r"D:\dt-trustworthy-maintenance")

PAIRS = [
    (MSA / "core/space/models.py", ROOT / "imported/msa_dti/space/models.py"),
    (MSA / "core/space/profile.py", ROOT / "imported/msa_dti/space/profile.py"),
    (MSA / "core/space/types.py", ROOT / "imported/msa_dti/space/types.py"),
    (MSA / "core/space/enumerator.py", ROOT / "imported/msa_dti/space/enumerator.py"),
    (
        MSA / "results/limited_validation_formal_protocol/candidate_bank/candidate_bank_manifest.json",
        ROOT / "imported/msa_dti/bank/candidate_bank_manifest.source.json",
    ),
    *[
        (
            MSA / f"results/limited_validation_formal_protocol/candidate_bank/assets/formal_h1_a{idx}.pt",
            ROOT / f"imported/msa_dti/bank/formal_h1_a{idx}.pt",
        )
        for idx in (1, 6, 46, 55, 56, 57, 62)
    ],
    (
        MSA / "outputs/final_e2e_c23_external_d2904_t2904/source_assets/medet_style_h1_a57.pt",
        ROOT / "imported/msa_dti/bank/medet_style_h1_a57.pt",
    ),
    (RAVM / "vendor/sim.py", ROOT / "imported/ravm_dt/sim.py"),
    (RAVM / "vendor/main_cfg.py", ROOT / "imported/ravm_dt/main_cfg.py"),
    (RAVM / "core/statistics.py", ROOT / "imported/ravm_dt/statistics.py"),
]


def sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    rows = []
    for source, destination in PAIRS:
        source_hash = sha256(source)
        destination_hash = sha256(destination)
        rows.append(
            {
                "source": source.as_posix(),
                "destination": destination.relative_to(ROOT).as_posix(),
                "source_sha256": source_hash,
                "destination_sha256": destination_hash,
                "exact_match": source_hash == destination_hash,
            }
        )
    result = {
        "schema": "dt-lifecycle-escalation/reuse-hash-manifest/v1",
        "all_exact_copies_match": all(row["exact_match"] for row in rows),
        "files": rows,
    }
    output = ROOT / "audits/reuse_hash_manifest.json"
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["all_exact_copies_match"]:
        raise SystemExit("reuse hash audit failed")


if __name__ == "__main__":
    main()
