"""Synthetic activation contracts and owned-process receipt tests only."""
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import activation as module
from queue_store import exclusive_json,read_json,sha


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_population_fixed_1200_order_all_methods(self):
        tasks=module.population()
        self.assertEqual(len(tasks),1200)
        self.assertEqual(len({tuple(t.items()) for t in tasks}),1200)
        self.assertEqual(tasks[0]['center_id'],33000);self.assertEqual(tasks[-1]['center_id'],33019)
        self.assertEqual([t['method'] for t in tasks[:5]],['B0','B1','B2','B8','P7.7'])
    def test_source_pin_mismatch_blocks(self):
        p=self.root/'source.py';p.write_text('SYNTHETIC')
        with self.assertRaises(Exception):module.verify_pins({str(p):'0'*64})
    def test_inventory_exact_known_scoped_and_caller_only(self):
        rows=[{'ProcessId':10,'CommandLine':str(module.REPO)+'/executor_worker.py'},
              {'ProcessId':11,'CommandLine':str(module.REPO)+'/activation.py'},
              {'ProcessId':12,'CommandLine':'python unrelated.py'}]
        self.assertEqual(module.producer_inventory(rows,11),[10])
    def test_inventory_unknown_scoped_producer_blocks(self):
        for command in (str(module.RESULTS)+'/unknown.py','python scripts/run_p7_7_final.py'):
            with self.assertRaises(Exception):
                module.producer_inventory([{'ProcessId':15,'CommandLine':command}],11)
    def test_inventory_inaccessible_command_blocks(self):
        with self.assertRaises(Exception):
            module.producer_inventory([{'ProcessId':15,'CommandLine':None}],11)
    def test_owned_nonzero_exit_preserved_without_model(self):
        contract=exclusive_json(self.root,'contract.json',{'run_relative':'SYNTHETIC'})
        child=SimpleNamespace(pid=1234,wait=lambda:19)
        with patch.object(module.subprocess,'Popen',return_value=child):
            with self.assertRaises(Exception):module.owned_run(contract,self.root,'synthetic')
        receipt=read_json(self.root/'synthetic_coordinator_exit.json')
        self.assertEqual(receipt['actual_exit_code'],19)
        self.assertFalse(receipt['automatic_retry'])
        self.assertEqual(receipt['contract_sha256'],contract['sha256'])
    def test_owned_zero_requires_actual_terminal_marker(self):
        contract=exclusive_json(self.root,'contract.json',{'run_relative':'execution/SYNTHETIC'})
        child=SimpleNamespace(pid=1234,wait=lambda:0)
        with patch.object(module,'RESULTS',self.root),patch.object(module.subprocess,'Popen',return_value=child):
            with self.assertRaises(Exception):module.owned_run(contract,self.root,'synthetic')
        self.assertEqual(read_json(self.root/'synthetic_coordinator_exit.json')['actual_exit_code'],0)
    def test_owned_zero_and_actual_marker_valid(self):
        path=self.root/'execution/SYNTHETIC';path.mkdir(parents=True)
        exclusive_json(path,'DYNAMIC_EXECUTION_COMPLETED.json',{'status':'DYNAMIC_TASKS_COMPLETED'})
        contract=exclusive_json(self.root,'contract.json',{'run_relative':'execution/SYNTHETIC'})
        child=SimpleNamespace(pid=1234,wait=lambda:0)
        with patch.object(module,'RESULTS',self.root),patch.object(module.subprocess,'Popen',return_value=child):
            start,end,marker=module.owned_run(contract,self.root,'synthetic')
        self.assertEqual(read_json(end['path'])['actual_exit_code'],0)
        self.assertTrue(marker.is_file())
    def test_frozen_inventory_rejects_unreceipted_csv(self):
        (self.root/'raw').mkdir();(self.root/'raw/SYNTHETIC.csv').write_text('partial')
        with self.assertRaises(Exception):module.saved_inventory(SimpleNamespace(root=self.root))


if __name__=='__main__':unittest.main()
