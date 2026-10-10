"""Isolated CUDA-2 test-only exercise of the production P7.6B trajectory worker.

Only IDs 90000--90005 are constructible. Formal assignment and result paths are
never used; the scientific trajectory function and claim/receipt code are.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.p7_6b_selected_data import selected_base_centers  # noqa: E402
from scripts import run_p7_6b as runner  # noqa: E402

TEST_START = 90000
TEST_COUNT = 6
TEST_IDS = (90000, 90001)
SEED = 7311
SCENARIO = "C0"
TEST_ROOT = ROOT / "results/p7_6b_r0_testonly"


def init_worker(out: str, mode: str) -> None:
    runner._worker_init("cuda", 1)
    runner.RESULTS = Path(out)
    bases = selected_base_centers(start=TEST_START, count=TEST_COUNT,
                                  selected_ids=list(TEST_IDS), data_seed=SEED)
    rows = {base.center_id: {"center_id": base.center_id,
                            "center_type": base.center_type,
                            "deployment_tier": base.budget_tier}
            for base in bases}
    assignment = {"pools": {"ReplicationFit": list(TEST_IDS)},
                  "candidate_stream": {"start": TEST_START, "count": TEST_COUNT,
                                       "data_seed": SEED},
                  "centers": list(rows.values())}

    def test_preflight(*, phase: str, require_opening: bool = False):
        if phase != "fit" or require_opening:
            raise RuntimeError("test-only harness forbids Validation")
        return assignment, {}

    runner.preflight = test_preflight
    if mode == "interrupt":
        from core import p7 as p7core
        original_step = p7core.DecisionExecutor.step_group

        def test_interruption(self, states, stage, update, assessment):
            if stage == 4:
                raise RuntimeError("TEST_ONLY_INJECTED_STAGE_4_INTERRUPTION")
            return original_step(self, states, stage, update, assessment)

        p7core.DecisionExecutor.step_group = test_interruption


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--mode", choices=("clean", "interrupt", "resume"), default="clean")
    parser.add_argument("--pair", choices=("distinct-centers", "same-center"),
                        default="distinct-centers")
    args = parser.parse_args()
    if not args.tag.replace("_", "").replace("-", "").isalnum():
        parser.error("tag must contain only letters, digits, underscores, or hyphens")
    out = TEST_ROOT / args.tag
    if args.mode == "resume":
        if not out.is_dir():
            raise RuntimeError("test-only resume directory does not exist")
    else:
        out.mkdir(parents=True, exist_ok=False)
    pairs = ((90000, "C0"), (90000, "C1")) if args.pair == "same-center" else (
        (90000, "C0"), (90001, "C0"))
    tasks = [runner.Task(center, SEED, scenario,
                         "test-only-protocol", "test-only-generator", "test-only-behavior")
             for center, scenario in pairs]
    print(json.dumps({"event": "test_only_start", "tasks": [task.key for task in tasks],
                      "workers": 2, "device": "cuda", "dtype": "float32",
                      "result_directory": str(out), "mode": args.mode,
                      "pair": args.pair}), flush=True)
    runner.RESULTS = out
    completed = sum(runner.validate_receipt("fit", task, "test-only-runtime") for task in tasks)
    pending = [task for task in tasks if not runner.validate_receipt("fit", task, "test-only-runtime")]
    runner.dispatch_pending("fit", pending, 2, "cuda", "test-only-runtime",
                            completed, len(tasks), initializer=init_worker,
                            initargs=(str(out), args.mode))
    if not all(runner.validate_receipt("fit", task, "test-only-runtime") for task in tasks):
        raise RuntimeError("test-only workload lacks complete receipts")
    remaining_claims = list((out / "raw/fit").glob("*.claim"))
    if remaining_claims:
        raise RuntimeError(f"orphan claims after successful test-only run: {remaining_claims}")
    print(json.dumps({"event": "test_only_finished", "completed": len(tasks),
                      "orphan_claims": 0, "mode": args.mode}), flush=True)


if __name__ == "__main__":
    main()
