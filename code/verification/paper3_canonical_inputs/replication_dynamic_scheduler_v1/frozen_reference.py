"""Bind scheduler integrity projections to existing F1 and initial certificates."""
from pathlib import Path
from queue_store import canonical, read_json, sha
from integrity import require


class FrozenReference:
    def __init__(self, manifest_path):
        self.path = Path(manifest_path).resolve(strict=True)
        self.manifest = read_json(self.path)
        m = self.manifest
        require(canonical({k: v for k, v in m.items() if k != 'manifest_digest'}) == m['manifest_digest'], 'manifest digest differs')
        self.root = Path(m['paths']['results_root']).resolve(strict=True)
        require(self.path == self.root / 'provenance_manifest.json', 'noncanonical manifest path')
        self.initial_path = self.root / 'initial_state_manifest.json'
        self.initial_sha = sha(self.initial_path)
        self.initial = read_json(self.initial_path)
        require(self.initial['manifest_digest'] == m['manifest_digest']
                and self.initial['input_bundle_digest'] == m['input_bundle_digest']
                and self.initial['completed_cases'] == 60, 'initial population differs')
        self.states = {(v['center_id'], v['seed']): v for v in self.initial['states']}
        require(len(self.states) == 60 and len(self.initial['states']) == 60, 'duplicate/missing initial states')
        runtime_path = self.root / self.initial['runtime_receipt_path']
        require(sha(runtime_path) == self.initial['runtime_receipt_sha256'], 'initial runtime bytes differ')
        self.runtime = read_json(runtime_path)['scientific_runtime']
        require(canonical(self.runtime) == self.initial['scientific_runtime_signature'], 'initial runtime signature differs')
        self.f1_path = Path(m['paths']['input_run']) / 'contexts/F1.json'
        require(sha(self.f1_path) == m['stage_b_bindings']['F1'], 'F1 context metadata bytes differ')
        self.f1 = read_json(self.f1_path)
        require(self.f1['input_bundle_digest'] == m['input_bundle_digest'], 'F1 population digest differs')

    def expected(self, task):
        m, f1 = self.manifest, self.f1
        center, seed, scene = task['center_id'], task['seed'], task['scenario']
        state = self.states[center, seed]
        base, scenario = f1['base'][str(center)], f1['scenarios'][f'{center}/{scene}']
        reference_rows = []
        for stage in range(1, 25):
            update = f1['roles'][f'{center}/{scene}/{stage}/update']
            row = {'scenario_hash': scenario['legacy_scenario_hash'], 'scenario_role': scenario['metadata']['definition'],
                   'center_type': base['profile']['center_type'], 'deployment_tier': base['profile']['budget_tier'],
                   'bank_hash': base['deployment']['bank_hash'], 'deployment_filter_hash': base['deployment']['deployment_filter_hash'],
                   'update_end_ts': str(update['update_end_ts']), 'decision_ts': str(update['decision_ts']),
                   'initial_state_hash': state['initial_state_hash']}
            for role, field in (('update','D_upd_hash'),('assessment','D_assess_hash'),('service','D_srv_hash')):
                row[field] = f1['roles'][f'{center}/{scene}/{stage}/{role}']['legacy_role_hash']
            reference_rows.append(row)
        critical = m['critical_files_sha256']
        rng_bindings = {'task': task, 'input_bundle_digest': m['input_bundle_digest'],
                        'source_bindings_digest': canonical(critical), 'environment_binding': m['environment_binding'],
                        'final_configuration_sha256': critical['configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json'],
                        'expected_initial_state_hash': state['initial_state_hash']}
        return {'manifest_digest': m['manifest_digest'], 'input_bundle_digest': m['input_bundle_digest'],
                'environment_binding': m['environment_binding'], 'initial_state_hash': state['initial_state_hash'],
                'initial_state_manifest_sha256': self.initial_sha, 'scientific_runtime_signature': self.initial['scientific_runtime_signature'],
                'scientific_runtime': self.runtime, 'critical_files_sha256': critical, 'source_bindings_digest': canonical(critical),
                'executor_bundle_digest': canonical(m['executor_sha256']), 'runner_hash': critical['scripts/run_p7_7_final.py'],
                'implementation_hash': critical['core/p7.py'], 'protocol_hash': critical['configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json'],
                'rng_bindings': rng_bindings, 'reference_rows': reference_rows}
