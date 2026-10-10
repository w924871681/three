"""Test-only P7.6B full-trajectory CPU/CUDA qualification.

Never imports or materializes the frozen 72-center assignment. IDs are fixed
to 90000--90005 and outputs live outside results/p7_6b.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TEST_START = 90000
TEST_COUNT = 6
OUT = ROOT / "results/p7_6b_qualification"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--center-id", type=int, default=TEST_START)
    parser.add_argument("--seed", type=int, default=7311)
    parser.add_argument("--scenario", choices=("C0", "C1", "C3", "C4"), default="C0")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    if not TEST_START <= args.center_id < TEST_START + TEST_COUNT:
        parser.error("only fixed test-only IDs 90000--90005 are permitted")
    if args.seed not in (7311, 7312, 7313) or args.threads not in (1, 2):
        parser.error("unsupported test-only seed/threads")
    if not args.tag.replace("-", "").replace("_", "").isalnum():
        parser.error("tag must be alphanumeric, underscore or hyphen")
    os.environ["OMP_NUM_THREADS"] = str(args.threads)
    os.environ["MKL_NUM_THREADS"] = str(args.threads)
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    if args.device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    import numpy as np
    import torch
    from core.common import array_digest, sha256_file
    from core.models import DEVICE, state_hash
    from core.p7_6b_selected_data import selected_base_centers
    from scripts import run_p7 as p7runner
    from scripts import run_p7_4b as p7b
    from scripts.run_p7_6b import atomic_bytes, atomic_json, read_json
    assert DEVICE.type == args.device, f"device mismatch {DEVICE} != {args.device}"
    torch.set_num_threads(args.threads)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(args.seed)
    if args.device == "cuda":
        torch.cuda.manual_seed_all(args.seed)
        torch.cuda.reset_peak_memory_stats()
    p7b.install_seed_binding()
    frozen = read_json(ROOT / "configs/p3_mismatch_v2_frozen.json")
    protocol = read_json(ROOT / "configs/p7_protocol.json")
    start = time.perf_counter()
    base = selected_base_centers(start=TEST_START, count=TEST_COUNT,
        selected_ids=[args.center_id], data_seed=7311)[0]
    base_hashes = {"x": array_digest(base.x), "y": array_digest(base.y),
                   "ts": array_digest(base.ts), "metadata": hashlib.sha256(
                        json.dumps(base.metadata, sort_keys=True).encode()).hexdigest()}
    print(json.dumps({"event": "generated", "center_id": args.center_id,
        "device": args.device, "elapsed_s": time.perf_counter() - start,
        "hashes": base_hashes}), flush=True)
    identities = p7b.bank(frozen)
    incumbent = next(x for x in identities if x.identity_id == "msa_a57_pt")
    reference = p7runner.reference(base, args.seed, incumbent, frozen)
    print(json.dumps({"event": "causal_reference_complete", "elapsed_s": time.perf_counter() - start,
        "reference_sha256": hashlib.sha256(json.dumps(reference, sort_keys=True).encode()).hexdigest()}), flush=True)
    from core import p7 as p7core
    original_step = p7core.DecisionExecutor.step_group
    diagnostic = []
    state_vectors = {}
    def vector(model):
        return np.concatenate([tensor.detach().cpu().contiguous().numpy().ravel()
                               for tensor in model.state_dict().values()]).astype(np.float32)
    def inspected_step(self, states, stage, update, assessment):
        output = original_step(self, states, stage, update, assessment)
        state, row, parent, probe, selected = output[0]
        candidates = []
        for (stage_key, idx, _update_hash, _assessment_hash), (model, loss, _duration) in self.source_cache.items():
            if stage_key == stage:
                state_vectors[f"stage_{stage}_candidate_{idx}"] = vector(model)
                candidates.append({"identity_id": self.bank[idx].identity_id,
                    "state_hash": state_hash(model), "assessment_loss": float(loss)})
        state_vectors[f"stage_{stage}_parent"] = vector(parent)
        state_vectors[f"stage_{stage}_probe"] = vector(probe)
        state_vectors[f"stage_{stage}_selected"] = vector(selected)
        diagnostic.append({"stage": stage, "parent_identity": row["identity_before"],
            "parent_state_hash": state_hash(parent), "probe_state_hash": state_hash(probe),
            "candidate_identities_and_hashes": sorted(candidates, key=lambda x: x["identity_id"]),
            "action": row["action"], "ri": int(row["ri"]),
            "post_action_identity": row["identity_after"],
            "post_action_state_hash": state_hash(selected),
            "D_upd_hash": row["D_upd_hash"], "D_assess_hash": row["D_assess_hash"]})
        print(json.dumps({"event": "stage_decision", "stage": stage,
            "action": row["action"], "ri": int(row["ri"]),
            "elapsed_s": time.perf_counter() - start}), flush=True)
        return output
    p7core.DecisionExecutor.step_group = inspected_step
    frame, scales = p7b.run_trajectory(base, args.seed, args.scenario, frozen, protocol,
                                        identities, float(reference["tau_service"]))
    if len(frame) != 24 or len(diagnostic) != 24:
        raise RuntimeError("complete 24-stage trajectory not produced")
    fields = ("stage", "identity_before", "parent_state_hash", "action", "ri",
              "identity_after", "deployed_state_hash", "A0_post_action_path_hash",
              "A1_post_action_path_hash", "A0_target", "A1_target", "A1_active_S_m",
              "R_B50", "D_srv_hash")
    missing = [x for x in fields if x not in frame.columns]
    if missing:
        raise RuntimeError(f"missing scientific comparison fields: {missing}")
    stagewise = frame[list(fields) + p7b.FEATURE_A0 + p7b.FEATURE_A1].to_dict(orient="records")
    tag_dir = OUT / args.tag
    tag_dir.mkdir(parents=True, exist_ok=False)
    traj = tag_dir / "trajectory.csv"
    scale_path = tag_dir / "scales.csv"
    diag_path = tag_dir / "candidate_diagnostics.json"
    stage_path = tag_dir / "stagewise.json"
    vector_path = tag_dir / "state_vectors.npz"
    atomic_bytes(traj, frame.to_csv(index=False, lineterminator="\n", float_format="%.17g").encode())
    atomic_bytes(scale_path, scales.to_csv(index=False, lineterminator="\n", float_format="%.17g").encode())
    atomic_json(diag_path, {"stages": diagnostic})
    atomic_json(stage_path, {"stages": stagewise})
    vector_blob = io.BytesIO()
    np.savez_compressed(vector_blob, **state_vectors)
    atomic_bytes(vector_path, vector_blob.getvalue())
    elapsed = time.perf_counter() - start
    summary = {"schema": "p7.6b-test-only-full-trajectory-v1", "test_only": True,
        "center_id": args.center_id, "seed": args.seed, "scenario": args.scenario,
        "device": args.device, "threads": args.threads, "stage_count": len(frame),
        "elapsed_seconds": elapsed, "base_hashes": base_hashes,
        "action_sequence": frame.action.tolist(), "ri_count": int(frame.ri.sum()),
        "files_sha256": {p.name: sha256_file(p) for p in (traj, scale_path, diag_path, stage_path, vector_path)},
        "peak_vram_MiB": (torch.cuda.max_memory_allocated() / 2**20 if args.device == "cuda" else 0.0),
        "heldout_accessed": False, "alibaba_accessed": False, "P8_executed": False}
    atomic_json(tag_dir / "summary.json", summary)
    print(json.dumps({"event": "complete", **summary}), flush=True)


if __name__ == "__main__":
    main()
