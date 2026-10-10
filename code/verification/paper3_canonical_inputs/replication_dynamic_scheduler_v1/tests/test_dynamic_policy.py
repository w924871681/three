"""Pure synthetic resource traces; no project import, model, IO control, or loss."""
from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("paper3_synthetic_dynamic_policy", HERE / "dynamic_policy.py")
p = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = p
SPEC.loader.exec_module(p)
GIB, MIB = p.GIB, p.MIB


def sample(t=0, *, commit=10*GIB, physical=6*GIB):
    return p.ResourceSample(t, commit, 32*GIB, physical, 16*GIB)


def worker(name="W1", phase="BUSY", *, private=3*GIB, peak=None,
           working=512*MIB, working_peak=None):
    return p.WorkerObservation(name, phase, private, private if peak is None else peak,
        working, working if working_peak is None else working_peak)


def observe(state, t, workers=(), *, commit=10*GIB, physical=6*GIB,
            tasks=100, config=None):
    return p.decide(config or p.PolicyConfig(), state, sample(t, commit=commit, physical=physical),
        tuple(workers), now_monotonic_ms=t, unclaimed_tasks=tasks)


def trace(times, workers=(), **kwargs):
    state = p.PolicyState()
    results = []
    for t in times:
        decision = observe(state, t, workers, **kwargs)
        results.append(decision)
        state = decision.next_state
    return results


class AdmissionTests(unittest.TestCase):
    def test_defaults_authorized_and_outcome_blind(self):
        config = p.PolicyConfig()
        self.assertEqual(config.max_workers, 3)
        self.assertEqual(config.planning_private_bytes, 7*GIB//2)
        self.assertEqual(config.commit_reserve_bytes, GIB)
        self.assertEqual(config.physical_reserve_bytes, GIB)
    def test_start_requires_three_distinct_healthy_samples(self):
        decisions = trace((0, 10_000, 20_000))
        self.assertEqual([d.action for d in decisions], ["WAIT_FOR_MEMORY", "WAIT_FOR_MEMORY", "ADMIT_ONE"])
        self.assertEqual(decisions[-1].target_worker_count, 1)
    def test_add_one_only(self):
        d = trace((0,10_000,20_000), (worker(),))[-1]
        self.assertEqual(d.action, "ADMIT_ONE")
        self.assertEqual(d.admit_count, 1)
        self.assertEqual(d.target_worker_count, 2)
    def test_three_workers_hard_cap(self):
        d = trace((0,10_000,20_000), tuple(worker(f"W{i}") for i in (1,2,3)))[-1]
        self.assertEqual(d.action, "HOLD")
        self.assertEqual(d.admit_count, 0)
    def test_commit_gate_inclusive_at_exact_threshold(self):
        d = trace((0,10_000,20_000), commit=9*GIB//2, physical=2*GIB)[-1]
        self.assertEqual(d.action, "ADMIT_ONE")
    def test_commit_one_byte_short_blocks(self):
        d = trace((0,10_000,20_000), commit=9*GIB//2-1)[-1]
        self.assertNotEqual(d.action, "ADMIT_ONE")
        self.assertFalse(d.resource_gate.admission_memory_pass)
    def test_physical_one_byte_short_blocks(self):
        d = trace((0,10_000,20_000), physical=2*GIB-1)[-1]
        self.assertNotEqual(d.action, "ADMIT_ONE")
    def test_commit_not_substituted_by_large_physical(self):
        d = trace((0,10_000,20_000), commit=GIB, physical=15*GIB)[-1]
        self.assertNotEqual(d.action, "ADMIT_ONE")
    def test_physical_not_substituted_by_large_commit(self):
        d = trace((0,10_000,20_000), commit=30*GIB, physical=GIB)[-1]
        self.assertNotEqual(d.action, "ADMIT_ONE")
    def test_no_unclaimed_tasks_no_admission(self):
        d = trace((0,10_000,20_000), tasks=0)[-1]
        self.assertEqual(d.action, "HOLD")
        self.assertFalse(d.dispatch_allowed)
    def test_pending_start_reserves_slot(self):
        admitted = trace((0,10_000,20_000), (worker(),))[-1]
        d = observe(admitted.next_state, 90_000, (worker(),))
        self.assertEqual(d.action, "WAIT_FOR_START")
        self.assertEqual(d.target_worker_count, 2)
        self.assertEqual(d.admit_count, 0)
    def test_real_new_identity_acknowledges_start(self):
        admitted = trace((0,10_000,20_000), (worker(),))[-1]
        d = observe(admitted.next_state, 30_000, (worker(),worker("W2","STARTING",private=0,working=0)))
        self.assertIsNone(d.next_state.pending_admission_from_ids)
        self.assertEqual(d.action, "HOLD")
    def test_starting_worker_not_additional_admission(self):
        workers = (worker("W1","STARTING",private=0,working=0),)
        d = trace((0,10_000,20_000), workers)[-1]
        self.assertEqual(d.action, "HOLD")
    def test_observed_private_peak_increases_budget(self):
        d = observe(p.PolicyState(), 0, (worker(peak=4*GIB),))
        self.assertEqual(d.resource_gate.per_worker_private_budget_bytes, 4*GIB+256*MIB)
        self.assertEqual(d.resource_gate.admission_free_commit_required_bytes, 5*GIB+256*MIB)
    def test_observed_working_peak_increases_physical_budget(self):
        d = observe(p.PolicyState(), 0, (worker(working_peak=2*GIB),))
        self.assertEqual(d.resource_gate.per_worker_working_set_budget_bytes, 2*GIB+256*MIB)
    def test_peak_memory_not_forgotten_after_worker_exit(self):
        d = observe(p.PolicyState(),0,(worker(peak=4*GIB,working_peak=2*GIB),))
        after = observe(d.next_state,10_000,())
        self.assertEqual(after.resource_gate.per_worker_private_budget_bytes,4*GIB+256*MIB)
        self.assertEqual(after.resource_gate.per_worker_working_set_budget_bytes,2*GIB+256*MIB)
    def test_larger_new_peak_resets_prior_healthy_streak(self):
        d = trace((0,10_000),(worker(),))[-1]
        after = observe(d.next_state,20_000,(worker(peak=4*GIB),))
        self.assertEqual(after.next_state.healthy_streak,1)
        self.assertNotEqual(after.action,"ADMIT_ONE")


class RetirementTests(unittest.TestCase):
    def test_pressure_blocks_dispatch_immediately(self):
        d = observe(p.PolicyState(),0,(worker(),),commit=GIB-1)
        self.assertFalse(d.dispatch_allowed)
        self.assertEqual(d.action,"HOLD_PRESSURE")
        self.assertFalse(d.in_flight_termination_permitted)
    def test_busy_worker_only_drains_after_three_low_samples(self):
        ds = trace((0,10_000,20_000),(worker(),),commit=GIB-1)
        self.assertEqual([d.action for d in ds],["HOLD_PRESSURE","HOLD_PRESSURE","DRAIN_ONE"])
        self.assertEqual(ds[-1].drain_worker_id,"W1")
        self.assertIsNone(ds[-1].retire_worker_id)
    def test_actual_retirement_only_at_idle_boundary(self):
        d = trace((0,10_000,20_000),(worker(),),commit=GIB-1)[-1]
        busy = observe(d.next_state,30_000,(worker(),),commit=GIB-1)
        self.assertEqual(busy.action,"WAIT_FOR_DRAIN_BOUNDARY")
        self.assertIsNone(busy.retire_worker_id)
        idle = observe(busy.next_state,40_000,(worker(phase="IDLE"),),commit=GIB-1)
        self.assertEqual(idle.action,"RETIRE_AT_BOUNDARY")
        self.assertEqual(idle.retire_worker_id,"W1")
    def test_idle_worker_retirement_does_not_touch_busy(self):
        workers = (worker("W1","BUSY",private=4*GIB),worker("W2","IDLE",private=2*GIB))
        d = trace((0,10_000,20_000),workers,physical=GIB-1)[-1]
        self.assertEqual(d.action,"RETIRE_AT_BOUNDARY")
        self.assertEqual(d.retire_worker_id,"W2")
        self.assertEqual(d.target_worker_count,1)
    def test_one_retirement_per_decision(self):
        workers = tuple(worker(f"W{i}","IDLE") for i in (1,2,3))
        d = trace((0,10_000,20_000),workers,commit=GIB-1)[-1]
        self.assertEqual(d.retire_worker_id,"W1")
        self.assertEqual(d.target_worker_count,2)
    def test_memory_tie_break_is_worker_identity(self):
        workers = (worker("W2","BUSY"),worker("W1","BUSY"))
        d = trace((0,10_000,20_000),workers,commit=GIB-1)[-1]
        self.assertEqual(d.drain_worker_id,"W1")
    def test_largest_commit_chosen_when_all_busy(self):
        workers = (worker("W1",private=2*GIB),worker("W2",private=3*GIB))
        d = trace((0,10_000,20_000),workers,commit=GIB-1)[-1]
        self.assertEqual(d.drain_worker_id,"W2")
    def test_recovered_memory_does_not_cancel_pending_drain(self):
        d = trace((0,10_000,20_000),(worker(),),commit=GIB-1)[-1]
        recovered = observe(d.next_state,30_000,(worker(),))
        self.assertEqual(recovered.action,"WAIT_FOR_DRAIN_BOUNDARY")
        self.assertEqual(recovered.drain_worker_id,"W1")
    def test_draining_observation_never_authorizes_termination(self):
        d = trace((0,10_000,20_000),(worker(phase="DRAINING"),),commit=GIB-1)[-1]
        self.assertNotEqual(d.action,"RETIRE_AT_BOUNDARY")
        self.assertFalse(d.in_flight_termination_permitted)
    def test_zero_workers_wait_when_pressure(self):
        d = trace((0,10_000,20_000),commit=GIB-1)[-1]
        self.assertEqual(d.action,"WAIT_FOR_MEMORY")
        self.assertEqual(d.target_worker_count,0)
    def test_last_worker_can_drain_for_safety(self):
        d = trace((0,10_000,20_000),(worker(),),commit=GIB-1)[-1]
        self.assertEqual(d.target_worker_count,0)
        self.assertEqual(d.action,"DRAIN_ONE")
    def test_starting_worker_not_killed_under_pressure(self):
        d = trace((0,10_000,20_000),(worker(phase="STARTING",private=0,working=0),),commit=GIB-1)[-1]
        self.assertEqual(d.action,"HOLD_PRESSURE")
        self.assertIsNone(d.retire_worker_id)
    def test_exact_reserve_is_not_pressure(self):
        d = observe(p.PolicyState(),0,(worker(),),commit=GIB,physical=GIB)
        self.assertFalse(d.resource_gate.pressure_present)
        self.assertTrue(d.dispatch_allowed)


class HysteresisTests(unittest.TestCase):
    def test_duplicate_sample_cannot_count_three_times(self):
        ds = trace((0,0,0))
        self.assertEqual(ds[-1].next_state.healthy_streak,1)
        self.assertNotEqual(ds[-1].action,"ADMIT_ONE")
    def test_too_close_samples_do_not_advance_streak(self):
        ds = trace((0,1000,2000,10_000))
        self.assertEqual(ds[-1].next_state.healthy_streak,2)
    def test_temporary_pressure_cancels_healthy_streak(self):
        d = trace((0,10_000))[-1]
        low = observe(d.next_state,11_000,commit=GIB-1)
        self.assertEqual(low.next_state.healthy_streak,0)
        self.assertFalse(low.dispatch_allowed)
        good = observe(low.next_state,20_000)
        self.assertNotEqual(good.action,"ADMIT_ONE")
    def test_temporary_recovery_cancels_pressure_streak(self):
        d = trace((0,10_000),(worker(),),commit=GIB-1)[-1]
        normal = observe(d.next_state,11_000,(worker(),))
        self.assertEqual(normal.next_state.pressure_streak,0)
    def test_scale_cooldown_blocks_addition(self):
        first = trace((0,10_000,20_000),(worker(),))[-1]
        state = first.next_state
        for t in (30_000,40_000,50_000,60_000,70_000):
            d = observe(state,t,(worker(),worker("W2")))
            self.assertNotEqual(d.action,"ADMIT_ONE")
            state = d.next_state
        final = observe(state,80_000,(worker(),worker("W2")))
        self.assertEqual(final.action,"ADMIT_ONE")
    def test_cooldown_does_not_allow_dispatch_under_pressure(self):
        first = trace((0,10_000,20_000),(worker(),))[-1]
        d = observe(first.next_state,30_000,(worker(),worker("W2")),commit=GIB-1)
        self.assertFalse(d.dispatch_allowed)
    def test_retirement_observed_exit_restarts_cooldown(self):
        d = trace((0,10_000,20_000),(worker(),),commit=GIB-1)[-1]
        gone = observe(d.next_state,30_000,())
        self.assertIsNone(gone.next_state.draining_worker_id)
        self.assertEqual(gone.next_state.last_scale_monotonic_ms,30_000)
        self.assertNotEqual(gone.action,"ADMIT_ONE")
    def test_hysteresis_middle_band_keeps_running_count(self):
        d = trace((0,10_000,20_000),(worker(),worker("W2")),commit=2*GIB,physical=2*GIB)[-1]
        self.assertEqual(d.action,"HOLD")
        self.assertEqual(d.target_worker_count,2)


class InputValidationTests(unittest.TestCase):
    def assert_invalid(self, call):
        with self.assertRaises(p.PolicyInputError):call()
    def test_max_four_forbidden(self):self.assert_invalid(lambda:p.PolicyConfig(max_workers=4))
    def test_private_floor_cannot_weaken(self):self.assert_invalid(lambda:p.PolicyConfig(planning_private_bytes=3*GIB))
    def test_commit_reserve_cannot_weaken(self):self.assert_invalid(lambda:p.PolicyConfig(commit_reserve_bytes=GIB-1))
    def test_physical_reserve_cannot_weaken(self):self.assert_invalid(lambda:p.PolicyConfig(physical_reserve_bytes=GIB-1))
    def test_three_real_samples_cannot_weaken(self):self.assert_invalid(lambda:p.PolicyConfig(consecutive_admission_samples=2))
    def test_duplicate_worker_rejected(self):self.assert_invalid(lambda:observe(p.PolicyState(),0,(worker(),worker())))
    def test_four_observed_workers_rejected(self):self.assert_invalid(lambda:observe(p.PolicyState(),0,tuple(worker(f"W{i}") for i in (1,2,3,4))))
    def test_bad_phase_rejected(self):self.assert_invalid(lambda:worker(phase="STOP_AND_KILL"))
    def test_running_worker_without_memory_rejected(self):self.assert_invalid(lambda:worker(private=0))
    def test_peak_below_current_rejected(self):self.assert_invalid(lambda:worker(peak=GIB))
    def test_negative_memory_rejected(self):self.assert_invalid(lambda:sample(commit=-1))
    def test_boolean_memory_rejected(self):self.assert_invalid(lambda:sample(commit=True))
    def test_free_above_capacity_rejected(self):self.assert_invalid(lambda:sample(commit=33*GIB))
    def test_stale_observation_rejected(self):
        self.assert_invalid(lambda:p.decide(p.PolicyConfig(),p.PolicyState(),sample(0),(),now_monotonic_ms=30_001,unclaimed_tasks=1))
    def test_future_observation_rejected(self):
        self.assert_invalid(lambda:p.decide(p.PolicyConfig(),p.PolicyState(),sample(10),(),now_monotonic_ms=0,unclaimed_tasks=1))
    def test_backwards_sample_rejected(self):
        d = observe(p.PolicyState(),10_000)
        self.assert_invalid(lambda:observe(d.next_state,9999))
    def test_same_timestamp_different_memory_rejected(self):
        d = observe(p.PolicyState(),0)
        self.assert_invalid(lambda:observe(d.next_state,0,commit=9*GIB))
    def test_policy_epoch_change_rejected(self):
        d = observe(p.PolicyState(),0)
        self.assert_invalid(lambda:observe(d.next_state,10_000,config=p.PolicyConfig(scale_cooldown_ms=120_000)))
    def test_invalid_task_count_rejected(self):self.assert_invalid(lambda:observe(p.PolicyState(),0,tasks=-1))
    def test_worker_identity_path_rejected(self):self.assert_invalid(lambda:worker(name="../other"))


class IndependenceTests(unittest.TestCase):
    def test_policy_has_only_standard_library_imports(self):
        tree = ast.parse((HERE/"dynamic_policy.py").read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node,ast.ImportFrom):names.add(node.module.split(".")[0])
        self.assertLessEqual(names,{"__future__","dataclasses","hashlib","json","re","typing"})
    def test_no_process_or_file_control_calls(self):
        tree = ast.parse((HERE/"dynamic_policy.py").read_text(encoding="utf-8"))
        called = set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                if isinstance(node.func,ast.Name):called.add(node.func.id)
                elif isinstance(node.func,ast.Attribute):called.add(node.func.attr)
        self.assertTrue(called.isdisjoint({"open","Popen","kill","terminate","system","exec","eval","read_text","write_text","manual_seed","set_rng_state","run_task"}))
    def test_api_accepts_no_model_outcomes(self):
        self.assertEqual(set(inspect.signature(p.decide).parameters),
            {"config","state","sample","workers","now_monotonic_ms","unclaimed_tasks"})
        with self.assertRaises(TypeError):p.ResourceSample(0,1,2,1,2,service_loss=0.01)
    def test_worker_order_does_not_change_decision(self):
        workers = (worker("W2","BUSY"),worker("W1","IDLE"))
        forward = trace((0,10_000,20_000),workers,commit=GIB-1)[-1]
        reverse = trace((0,10_000,20_000),workers[::-1],commit=GIB-1)[-1]
        self.assertEqual(forward,reverse)
    def test_repeated_trace_is_exactly_deterministic(self):
        args = ((0,10_000,20_000),(worker(),))
        self.assertEqual(trace(*args),trace(*args))
    def test_inputs_remain_unchanged(self):
        config,state,s,workers = p.PolicyConfig(),p.PolicyState(),sample(),(worker(),)
        before = (asdict(config),asdict(state),asdict(s),tuple(asdict(w) for w in workers))
        p.decide(config,state,s,workers,now_monotonic_ms=0,unclaimed_tasks=1)
        after = (asdict(config),asdict(state),asdict(s),tuple(asdict(w) for w in workers))
        self.assertEqual(before,after)
    def test_all_intents_forbid_inflight_termination_and_outcomes(self):
        for ds in (trace((0,10_000,20_000)),trace((0,10_000,20_000),(worker(),),commit=GIB-1),
                   trace((0,10_000,20_000),(worker(phase="IDLE"),),physical=GIB-1)):
            for d in ds:
                self.assertFalse(d.in_flight_termination_permitted)
                self.assertFalse(d.model_outcomes_used)
    def test_decision_is_json_serializable(self):
        d = trace((0,10_000,20_000),(worker(),))[-1]
        value=json.loads(json.dumps(asdict(d),sort_keys=True,allow_nan=False))
        self.assertEqual(value["action"],"ADMIT_ONE")


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--proof-output",type=Path);args=parser.parse_args()
    files=(HERE/"dynamic_policy.py",Path(__file__).resolve())
    before={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    started=datetime.now(timezone.utc).isoformat()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    after={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    assert before==after
    if args.proof_output:
        out=args.proof_output.resolve();assert out.parent==HERE and not out.exists()
        proof={"schema":"paper3-dynamic-memory-policy-synthetic-test-proof-v1",
            "all_pass":result.wasSuccessful() and not result.skipped,"tests_run":result.testsRun,
            "failures":len(result.failures),"errors":len(result.errors),"skipped":len(result.skipped),
            "started_utc":started,"finished_utc":datetime.now(timezone.utc).isoformat(),
            "implementation_sha256":after,"real_models_or_generators_or_statistics_executed":False,
            "real_workers_or_processes_modified":False,"real_results_written":False,
            "policy_config":asdict(p.PolicyConfig()),"policy_config_fingerprint":p.PolicyConfig().fingerprint}
        with out.open("x",encoding="utf-8",newline="\n") as stream:
            json.dump(proof,stream,sort_keys=True,indent=2);stream.write("\n")
    raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)


if __name__=="__main__":main()
