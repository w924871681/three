"""Pure fake-backend tests; no project/scientific modules or real asset locks."""
import copy
import hashlib
import pickle
from pathlib import Path
import threading
import unittest

from session import ReuseError, TreeSpec, ValidationSession


MANIFEST = "f" * 64
ROOT = str(Path(__file__).absolute().parent / "FAKE_ONLY_TREE")
FILE = str(Path(ROOT) / "data.bin")
SOURCE = str(Path(ROOT) / "verifier.py")
OUTPUT = str(Path(ROOT).parent / "FAKE_ONLY_OUTPUT" / "new.json")
COUNTERS = {}


class FakeBackend:
    def __init__(self):
        self.contents = {FILE: b"fixed input", SOURCE: b"reviewed original verifier"}
        self.handles = {}
        self.identities = {}
        self.opens = 0
        self.closes = 0
        self.hashes = 0
        self.file_bytes_read = 0
        self.process = (1234, 987654321)
        self.tree_entries = {"data.bin": "file", "verifier.py": "file"}
        self.fail_open_at = None
        self.fail_close_once = False
        self.reparse = set()
        self.on_inventory = None
        self.inventory_calls = 0
        self.pending = []
        self.directories = {str(p) for p in Path(ROOT).parents} | {ROOT, str(Path(OUTPUT).parent)}

    def process_identity(self):
        return self.process

    def pending_cleanup(self):
        return tuple(dict(item) for item in self.pending)

    def path_exists(self, path):
        return str(path) in self.contents or str(path) in self.directories

    @staticmethod
    def same_file_identity(first, second):
        return (first["volume"], first["file_id"]) == (second["volume"], second["file_id"])

    def open_read(self, path, *, directory):
        self.opens += 1
        if self.fail_open_at == self.opens or path in self.reparse:
            raise ReuseError("synthetic acquisition denied")
        handle = self.opens
        self.handles[handle] = str(path)
        self.identities.setdefault(str(path), {"directory": directory, "file_id": str(path),
            "size": 0 if directory else len(self.contents[str(path)]), "volume": 99})
        return handle

    def identity(self, handle):
        if handle not in self.handles:
            raise ReuseError("synthetic closed handle")
        return dict(self.identities[self.handles[handle]])

    def close(self, handle):
        if self.fail_close_once:
            self.fail_close_once = False
            raise ReuseError("synthetic close failure")
        if handle not in self.handles:
            raise ReuseError("synthetic unknown handle")
        del self.handles[handle]
        self.pending = [item for item in self.pending if item["handle"] != handle]
        self.closes += 1

    def inventory(self, tree):
        self.inventory_calls += 1
        if self.on_inventory:
            self.on_inventory(self)
        return dict(self.tree_entries)

    def hash_file(self, path):
        self.hashes += 1
        self.file_bytes_read += len(self.contents[str(path)])
        return hashlib.sha256(self.contents[str(path)]).hexdigest()


class Fixture:
    def __init__(self):
        self.backend = FakeBackend()
        self.full_calls = 0
        self.runtime_calls = 0
        self.numeric_calls = 0
        self.full_result = {"manifest_digest": MANIFEST, "critical_scientific_bytes_unchanged": True,
            "environment_file_bytes_checked": True, "original_full_snapshot_checked": True, "all_F1_inputs_checked": True}
        self.runtime_result = {"manifest_digest": MANIFEST, "runtime_semantics_checked": True}
        self.full_raises = False
        self.runtime_raises = False
        self.on_full = None
        self.bindings = {p: hashlib.sha256(v).hexdigest() for p, v in self.backend.contents.items()}
        self.tree = TreeSpec(ROOT, self.backend.tree_entries)

    def full(self):
        self.full_calls += 1
        if self.full_raises:
            raise ReuseError("synthetic full callback failure")
        if self.on_full:
            self.on_full(self)
        return dict(self.full_result)

    def runtime(self):
        self.runtime_calls += 1
        if self.runtime_raises:
            raise ReuseError("synthetic runtime failure")
        return dict(self.runtime_result)

    def make(self, **changes):
        options = {"bindings": self.bindings, "trees": [self.tree], "manifest_digest": MANIFEST,
            "verifier_sources": {SOURCE: self.bindings[SOURCE]}, "original_full_verify": self.full,
            "runtime_verify": self.runtime, "backend": self.backend, "accept_documented_native_limitations": True}
        options.update(changes)
        return ValidationSession(**options)


class SessionTests(unittest.TestCase):
    def test_ten_metadata_boundaries_zero_full_or_byte_reads(self):
        f = Fixture()
        with f.make() as session:
            initial_hashes, initial_bytes = f.backend.hashes, f.backend.file_bytes_read
            for n in range(10):
                observation = session.boundary("boundary-" + str(n))
                self.assertTrue(observation["boundary_metadata_is_not_new_SHA_equality_proof"])
            self.assertEqual(f.full_calls, 1)
            self.assertEqual(f.backend.hashes, initial_hashes)
            self.assertEqual(f.backend.file_bytes_read, initial_bytes)
            with session.publication_guard(output_paths=[OUTPUT]) as proof:
                self.assertEqual(proof["original_full_and_complete_SHA_bookends_passed"], 2)
            self.assertEqual(session.state, "SEALED")
            COUNTERS.update({"synthetic_full_callbacks_initial_and_final": f.full_calls,
                "intermediate_boundaries": 10, "intermediate_full_callbacks": 0,
                "intermediate_protected_file_content_reads": 0, "intermediate_protected_bytes_read": 0,
                "synthetic_model_statistics_numerical_calls": f.numeric_calls,
                "total_full_binding_hash_reads": f.backend.hashes, "protected_files": len(f.bindings)})
        self.assertEqual(f.backend.handles, {})

    def test_all_handles_precede_initial_full(self):
        f = Fixture()
        f.on_full = lambda owner: self.assertTrue(set(owner.backend.contents) <= set(owner.backend.handles.values()))
        with f.make():
            pass

    def test_no_retroactive_receipt_init(self):
        f = Fixture()
        with self.assertRaises(ReuseError):
            f.make(original_full_verify={"status": "PASS"})

    def test_requires_fresh_runtime_validator(self):
        with self.assertRaises(ReuseError):
            Fixture().make(runtime_verify=None)

    def test_requires_explicit_native_limits(self):
        with self.assertRaises(ReuseError):
            Fixture().make(accept_documented_native_limitations=False)

    def test_partial_acquisition_closes_all(self):
        f = Fixture()
        f.backend.fail_open_at = 3
        s = f.make()
        with self.assertRaises(ReuseError):
            s.start()
        self.assertEqual(s.state, "FAILED")
        self.assertEqual(f.backend.handles, {})
        self.assertEqual(f.full_calls, 0)

    def test_original_full_failure_poison(self):
        f = Fixture()
        f.full_raises = True
        s = f.make()
        with self.assertRaises(ReuseError):
            s.start()

    def test_second_start_poison_and_release(self):
        f = Fixture(); s = f.make(); s.start()
        with self.assertRaises(ReuseError): s.start()
        self.assertEqual(s.state, "FAILED"); self.assertFalse(f.backend.handles)
        self.assertEqual(s.state, "FAILED")
        self.assertFalse(f.backend.handles)
        with self.assertRaises(ReuseError):
            s.start()

    def test_partial_four_closure_not_pass(self):
        for key in ("critical_scientific_bytes_unchanged", "environment_file_bytes_checked",
                    "original_full_snapshot_checked", "all_F1_inputs_checked"):
            with self.subTest(key=key):
                f = Fixture(); f.full_result[key] = False; s = f.make()
                with self.assertRaises(ReuseError): s.start()
                self.assertFalse(f.backend.handles)

    def test_wrong_manifest_rejected(self):
        f = Fixture(); f.full_result["manifest_digest"] = "0" * 64
        with self.assertRaises(ReuseError): f.make().start()
        self.assertFalse(f.backend.handles)

    def test_initial_bytes_mismatch_rejected(self):
        f = Fixture(); f.backend.contents[FILE] = b"different"
        with self.assertRaises(ReuseError): f.make().start()
        self.assertFalse(f.backend.handles)

    def test_initial_post_full_inventory_race_rejected(self):
        f = Fixture(); f.on_full = lambda owner: owner.backend.tree_entries.update({"unexpected": "file"})
        with self.assertRaises(ReuseError): f.make().start()
        self.assertFalse(f.backend.handles)

    def test_added_file_rejected_at_boundary(self):
        f = Fixture(); s = f.make(); s.start(); f.backend.tree_entries["new.bin"] = "file"
        with self.assertRaises(ReuseError): s.boundary("added")
        self.assertEqual(s.state, "FAILED"); self.assertFalse(f.backend.handles)

    def test_removed_file_rejected(self):
        f = Fixture(); s = f.make(); s.start(); del f.backend.tree_entries["data.bin"]
        with self.assertRaises(ReuseError): s.boundary("removed")

    def test_empty_directory_addition_rejected(self):
        f = Fixture(); s = f.make(); s.start(); f.backend.tree_entries["empty"] = "directory"
        with self.assertRaises(ReuseError): s.boundary("empty-dir")

    def test_file_id_change_rejected(self):
        f = Fixture(); s = f.make(); s.start(); f.backend.identities[FILE]["file_id"] = "replacement"
        with self.assertRaises(ReuseError): s.boundary("replaced")
        self.assertFalse(f.backend.handles)

    def test_ancestor_identity_change_rejected(self):
        f = Fixture(); s = f.make(); s.start(); f.backend.identities[ROOT]["volume"] = 100
        with self.assertRaises(ReuseError): s.boundary("directory-volume")

    def test_reparse_replacement_rejected(self):
        f = Fixture(); s = f.make(); s.start(); f.backend.reparse.add(FILE)
        with self.assertRaises(ReuseError): s.boundary("reparse")
        self.assertFalse(f.backend.handles)

    def test_lost_held_handle_poison(self):
        f = Fixture(); s = f.make(); s.start(); del f.backend.handles[next(iter(f.backend.handles))]
        with self.assertRaises(ReuseError): s.boundary("closed")
        self.assertEqual(s.state, "FAILED")
        self.assertTrue(s.observation()["close_errors"])

    def test_runtime_failure_at_boundary_poison(self):
        f = Fixture(); s = f.make(); s.start(); f.runtime_result["runtime_semantics_checked"] = False
        with self.assertRaises(ReuseError): s.boundary("environment")
        self.assertFalse(f.backend.handles)

    def test_runtime_exception_poison(self):
        f = Fixture(); s = f.make(); s.start(); f.runtime_raises = True
        with self.assertRaises(ReuseError): s.boundary("environment")

    def test_same_pid_different_creation_rejected(self):
        f = Fixture(); s = f.make(); s.start(); f.backend.process = (1234, 987654322)
        with self.assertRaises(ReuseError): s.boundary("PID-reuse")
        self.assertFalse(f.backend.handles)

    def test_other_process_rejected(self):
        f = Fixture(); s = f.make(); s.start(); f.backend.process = (9999, 987654321)
        with self.assertRaises(ReuseError): s.boundary("other-process")

    def test_cross_thread_rejected(self):
        f = Fixture(); s = f.make(); s.start(); errors = []
        def other():
            try: s.boundary("thread")
            except ReuseError as error: errors.append(str(error))
        t = threading.Thread(target=other); t.start(); t.join()
        self.assertEqual(len(errors), 1); self.assertEqual(s.state, "FAILED"); self.assertFalse(f.backend.handles)

    def test_no_pickle_or_copy(self):
        f = Fixture(); s = f.make()
        for operation in (lambda: pickle.dumps(s), lambda: copy.copy(s), lambda: copy.deepcopy(s)):
            with self.assertRaises(ReuseError): operation()

    def test_observation_cannot_initialize_session(self):
        f = Fixture(); s = f.make(); observation = s.observation()
        with self.assertRaises(ReuseError): f.make(original_full_verify=observation)
        self.assertTrue(observation["JSON_observation_is_not_a_cache_token"])

    def test_external_bindings_input_mutation_not_reflected(self):
        f = Fixture(); s = f.make(); f.bindings[FILE] = "0" * 64
        self.assertNotEqual(s.bindings[FILE], f.bindings[FILE])
        with self.assertRaises(TypeError): s.bindings[FILE] = "1" * 64

    def test_tree_mutation_not_reflected(self):
        source = {"file": "file"}; t = TreeSpec(ROOT, source); source["new"] = "directory"
        self.assertNotIn("new", t.entries)

    def test_source_not_protected_rejected(self):
        with self.assertRaises(ReuseError): Fixture().make(verifier_sources={SOURCE: "0" * 64})

    def test_unbound_inventory_file_rejected(self):
        with self.assertRaises(ReuseError): Fixture().make(trees=[TreeSpec(ROOT, {"unbound": "file"})])

    def test_malformed_tree_paths_rejected(self):
        for path in ("../bad", "/bad", "a\\b", "a//b", "a/./b", "C:/bad"):
            with self.subTest(path=path), self.assertRaises(ReuseError): TreeSpec(ROOT, {path: "file"})

    def test_deny_publication_into_protected_tree(self):
        f = Fixture(); s = f.make(); s.start()
        with self.assertRaises(ReuseError):
            with s.publication_guard(output_paths=[FILE]): pass
        self.assertFalse(f.backend.handles)

    def test_case_alias_protected_file_outside_tree_rejected(self):
        f = Fixture(); outside = str(Path(ROOT).parent / "OUTSIDE_PROTECTED.bin")
        f.backend.contents[outside] = b"protected outside tree"
        f.bindings[outside] = hashlib.sha256(f.backend.contents[outside]).hexdigest()
        s = f.make(); s.start()
        with self.assertRaises(ReuseError):
            with s.publication_guard(output_paths=[outside.swapcase()]): pass
        self.assertFalse(f.backend.handles)

    def test_case_alias_output_duplicates_rejected(self):
        f = Fixture(); s = f.make(); s.start()
        with self.assertRaises(ReuseError):
            with s.publication_guard(output_paths=[OUTPUT, OUTPUT.swapcase()]): pass

    def test_existing_hardlink_alias_output_rejected(self):
        f = Fixture(); f.backend.contents[OUTPUT] = f.backend.contents[FILE]
        s = f.make(); s.start(); f.backend.identities[OUTPUT] = dict(f.backend.identities[FILE])
        with self.assertRaises(ReuseError):
            with s.publication_guard(output_paths=[OUTPUT]): pass

    def test_output_parent_reparse_rejected_before_publication(self):
        f = Fixture(); s = f.make(); s.start(); f.backend.reparse.add(str(Path(OUTPUT).parent))
        with self.assertRaises(ReuseError):
            with s.publication_guard(output_paths=[OUTPUT]): self.fail("reparse output allowed")
        self.assertFalse(f.backend.handles)

    def test_missing_output_parent_rejected_before_publication(self):
        f = Fixture(); s = f.make(); s.start(); f.backend.directories.remove(str(Path(OUTPUT).parent))
        with self.assertRaises(ReuseError):
            with s.publication_guard(output_paths=[OUTPUT]): self.fail("missing parent allowed")

    def test_publication_original_full_required_again(self):
        f = Fixture(); s = f.make(); s.start(); f.full_raises = True
        published = []
        with self.assertRaises(ReuseError):
            with s.publication_guard(output_paths=[OUTPUT]): published.append(True)
        self.assertFalse(published); self.assertFalse(f.backend.handles); self.assertEqual(f.full_calls, 2)

    def test_untrusted_same_metadata_byte_change_detected_at_final(self):
        f = Fixture(); s = f.make(); s.start()
        # Synthetic malicious/native bypass is outside deny-write protection;
        # metadata MUST NOT claim detection or equal bytes. Final SHA catches it.
        f.backend.contents[FILE] = b"other input"
        observation = s.boundary("metadata-only")
        self.assertTrue(observation["boundary_metadata_is_not_new_SHA_equality_proof"])
        with self.assertRaises(ReuseError):
            with s.publication_guard(output_paths=[OUTPUT]): self.fail("must not publish")

    def test_publication_exception_closes_all(self):
        f = Fixture(); s = f.make(); s.start()
        with self.assertRaises(ValueError):
            with s.publication_guard(output_paths=[OUTPUT]): raise ValueError("publication failed")
        self.assertEqual(s.state, "FAILED"); self.assertFalse(f.backend.handles)

    def test_postpublication_mutation_failure(self):
        f = Fixture(); s = f.make(); s.start()
        with self.assertRaises(ReuseError):
            with s.publication_guard(output_paths=[OUTPUT]): f.backend.tree_entries["unexpected"] = "file"
        self.assertEqual(s.state, "FAILED"); self.assertFalse(f.backend.handles)

    def test_no_second_publication_without_new_epoch(self):
        f = Fixture(); s = f.make(); s.start()
        with s.publication_guard(output_paths=[OUTPUT]): pass
        with self.assertRaises(ReuseError):
            with s.publication_guard(output_paths=[OUTPUT]): pass

    def test_context_exception_cleanup(self):
        f = Fixture()
        with self.assertRaises(ValueError):
            with f.make(): raise ValueError("consumer failure")
        self.assertFalse(f.backend.handles)

    def test_close_releases_all_and_disallows_boundary(self):
        f = Fixture(); s = f.make(); s.start(); s.close()
        self.assertFalse(f.backend.handles)
        with self.assertRaises(ReuseError): s.boundary("closed")

    def test_close_failure_not_silently_forgotten(self):
        f = Fixture(); s = f.make(); s.start(); f.backend.fail_close_once = True
        with self.assertRaises(ReuseError): s.close()
        self.assertEqual(s.state, "FAILED"); self.assertEqual(len(f.backend.handles), 1)
        with self.assertRaises(ReuseError): s.close()
        self.assertFalse(f.backend.handles)

    def test_fresh_probe_close_failure_tracked_and_retried(self):
        f = Fixture(); s = f.make(); s.start(); f.backend.fail_close_once = True
        with self.assertRaises(ReuseError): s.boundary("fresh-probe-close-failure")
        self.assertEqual(s.state, "FAILED"); self.assertFalse(f.backend.handles)
        self.assertTrue(any(item.get("kind") == "temporary" for item in s.observation()["close_errors"]))

    def test_failed_open_pending_handle_cleanup(self):
        f = Fixture(); original_open = f.backend.open_read
        def fail_open(path, *, directory):
            handle = original_open(path, directory=directory)
            f.backend.pending.append({"handle": handle, "path": str(path), "kind": "backend_open_rejection",
                "error_type": "ReuseError", "message": "synthetic initial cleanup failure"})
            raise ReuseError("synthetic identity and cleanup failed")
        f.backend.open_read = fail_open
        s = f.make()
        with self.assertRaises(ReuseError): s.start()
        self.assertFalse(f.backend.handles); self.assertTrue(s.observation()["close_errors"])


if __name__ == "__main__":
    unittest.main()
