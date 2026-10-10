"""Private metadata adaptation; original numerical statistics remain byte-frozen."""
from __future__ import annotations
import argparse
import importlib.util
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('paper3_dynamic_sequence_api',HERE/'dynamic_sequence.py')
s=importlib.util.module_from_spec(spec);sys.modules[spec.name]=s;spec.loader.exec_module(s)

def install_origin_extension(guard,allowed):
    """Add exact SHA-bound metadata files only; retain every original rejection."""
    original=guard.allowed_module_origin
    allowed={str(Path(n).resolve()).casefold():h for n,h in allowed.items()}
    def origin(fullname,path,**contract):
        if original(fullname,path,**contract): return True
        key=str(Path(path).resolve()).casefold()
        return key in allowed and contract['bound'].get(key)==allowed[key] and s.sha(path)==allowed[key]
    guard.allowed_module_origin=origin
    install=guard.install_statistics_import_guard
    def wrapped(manifest,bindings,p):
        proof=install(manifest,bindings,p)
        proof['numpy_and_stdlib_only']=False
        proof.update(numerical_dependencies_numpy_and_stdlib_only=True,
                     metadata_origin_extension='ORIGINAL_STATISTICS_GUARD_PLUS_EXACT_DYNAMIC_DELIVERY_SIDECAR_SHA256',
                     metadata_source_sha256=allowed,model_generator_imports_forbidden=True)
        return proof
    guard.install_statistics_import_guard=wrapped

def configure(plan,c):
    root=s.BASE/'replication_statistics_batch20_env_v3'; name='paper3_dynamic_frozen_statistics'
    s.package(name,root)
    stats=s.load_module(root/'statistics.py',name+'.statistics',s.ORIGINAL['replication_statistics_batch20_env_v3/statistics.py'])
    guard=s.load_module(root/'runtime_guard.py',name+'.runtime_guard',s.ORIGINAL['replication_statistics_batch20_env_v3/runtime_guard.py'])
    original_phase=stats._phase_evidence
    certificate=Path(plan['record_root'])/'DYNAMIC_FULL_INTEGRITY_CERTIFICATE.json'
    def phase(p,bindings,manifest,phase,expected_tasks):
        if phase!='full': return original_phase(p,bindings,manifest,phase,expected_tasks)
        return s.full_history(plan,c,p,bindings,manifest,expected_tasks,certificate)
    stats._phase_evidence=phase
    allowed={str(HERE/n):plan['implementation_sha256'][str(HERE/n)] for n in ('dynamic_sequence.py','dynamic_statistics_route.py')}
    qp=s.BASE/'replication_dynamic_scheduler_v1/queue_store.py'; allowed[str(qp)]=c['sidecar_sources'][str(qp)]
    install_origin_extension(guard,allowed)
    return stats
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--plan',required=True);args=ap.parse_args()
    s.require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'requires -I -S -B')
    plan,c=s.verify_plan(args.plan);plan['_plan_path']=str(s.safe(args.plan))
    p,d=s.original_modules();manifest=p.read_json(s.RESULTS/'provenance_manifest.json')
    s.verify_dynamic_terminal(plan,c,d,manifest)
    stats=configure(plan,c)
    receipt=stats.run_statistics(s.REPO,s.RESULTS,expected_manifest_digest=s.MANIFEST)
    print(s.json.dumps(receipt,sort_keys=True),flush=True)
if __name__=='__main__':main()
