"""Saved-result delivery and locked root publication for an actual dynamic terminal."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
if 'paper3_dynamic_sequence_api' in sys.modules:s=sys.modules['paper3_dynamic_sequence_api']
else:
    spec=importlib.util.spec_from_file_location('paper3_dynamic_sequence_api',HERE/'dynamic_sequence.py')
    s=importlib.util.module_from_spec(spec);sys.modules[spec.name]=s;spec.loader.exec_module(s)

def phase_rows(api,root,bindings,digest,plan,c,terminal):
    rows=[];original_artifact=api._original_phase_artifact
    for n,h in sorted(bindings.items()):
        path=Path(n); identity=original_artifact(root,path) if not path.resolve().is_relative_to(s.RESULTS/'execution/dynamic') else None
        if not identity or path.name not in ('completion.json','failure.json'):continue
        api.bound_bytes(path,h); value=api.load_json(path)
        s.require(value.get('manifest_digest')==digest and value.get('phase')==identity[0] and value.get('attempt_id')==identity[1],'preserved phase identity differs')
        external=value.get('original_driver_terminal_record') is False or value.get('producer')=='EXTERNAL_PHASE_OBSERVER'
        if external:s.require(path.name=='failure.json' and value.get('success',False) is False and value.get('exit_code') is None and value.get('child_exit_code') is None,'external observer cannot assert success or exit')
        start=value.get('start') or value.get('started');finish=value.get('finish') if not external else None
        if not external:finish=finish or value.get('finished')
        s.require(start,'phase starting timestamp absent')
        for stamp in (start,finish):
            if stamp:s.require(s.datetime.fromisoformat(stamp).tzinfo is not None,'phase timestamp timezone absent')
        rows.append({'phase':identity[0],'attempt':identity[1],'start':start,'finish':finish or 'NOT_VERIFIED',
                     'worker_count':value.get('worker_count','NOT_RECORDED_FOR_FAILURE'),'success':value.get('success',False),
                     'failure':value.get('error',''),'source_path':n,'sha256':h,
                     'external_observation_cutoff':value.get('finished') if external else None,'actual_exit':'NOT_VERIFIED' if external else 'ORIGINAL_TERMINAL_RECEIPT'})
    for phase in ('initial','minimal'):s.require(any(r['phase']==phase and r['success'] is True for r in rows),'original small-phase completion absent')
    static_start=s.BASE/'autonomous_replication_execution_20261009_v3/phase_launches/full_002/start.json'
    s.require(bindings.get(str(static_start))==s.sha(static_start),'actual full002 launch is not bound by statistics')
    original_start=s.read(static_start);s.require(original_start.get('phase')=='full' and original_start.get('attempt')==2 and original_start.get('workers')==2,'actual full002 launch identity differs')
    quiescence=s.read(plan['quiescence_path']);termination_ref=quiescence['termination_evidence'];termination=s.read(s.bound(termination_ref['path'],termination_ref['sha256']))
    s.require(termination.get('schema')=='paper3-intentional-cutover-native-termination-v1' and termination.get('all_twelve_old_owners_dead') is True and
              termination.get('normal_completion_claimed') is False and termination.get('worker_exception_invented') is False,'actual controlled termination evidence differs')
    s.require(not any(r['attempt']=='A_FULL_0002' for r in rows),'static full002 already has a terminal; takeover lineage ambiguous')
    rows.append({'phase':'full','attempt':'A_FULL_0002','start':original_start['started_utc'],'finish':termination['created_utc'],
                 'worker_count':2,'success':False,'failure':'INTENTIONALLY_INTERRUPTED_FOR_AUTHORIZED_DYNAMIC_TAKEOVER',
                 'source_path':termination_ref['path'],'sha256':termination_ref['sha256'],'external_observation_cutoff':None,
                 'actual_exit':'IDENTITY_PINNED_NATIVE_TERMINATION_OBSERVED','retained_tasks':terminal['retained_lineage'].get('A_FULL_0002',0),
                 'completed_dynamic_tasks':0})
    smoke=s.read(plan['smoke_certificate_path']);smoke_end_ref=smoke['actual_coordinator_exit'];smoke_end=s.read(s.bound(smoke_end_ref['path'],smoke_end_ref['sha256']))
    smoke_start_path=Path(smoke_end_ref['path']).with_name('smoke_coordinator_start.json');smoke_start=s.read(smoke_start_path)
    s.require(bindings.get(str(smoke_start_path))==s.sha(smoke_start_path) and smoke_end.get('start_receipt_sha256')==s.sha(smoke_start_path),'smoke owned start is not statistics-bound')
    s.validate_owner(smoke_start,smoke_end,smoke['contract']['sha256'],active=s.process_active)
    rows.append({'phase':'full','attempt':'A_DYNAMIC_0001_BRIDGE_SMOKE','start':smoke_start['started_utc'],'finish':smoke_end['finished_utc'],
                 'worker_count':1,'success':True,'failure':'','source_path':smoke_end_ref['path'],'sha256':smoke_end_ref['sha256'],
                 'external_observation_cutoff':None,'actual_exit':'OWNING_POPEN_WAIT_ZERO','retained_tasks':1,'completed_dynamic_tasks':0})
    rows.append({'phase':'full','attempt':c['attempt_id'],'start':terminal['coordinator_start']['started_utc'],
                 'finish':terminal['coordinator_exit']['finished_utc'],'worker_count':'DYNAMIC_0_TO_3','success':True,'failure':'',
                 'source_path':plan['coordinator_exit_path'],'sha256':s.sha(plan['coordinator_exit_path']),
                 'external_observation_cutoff':None,
                 'actual_exit':'OWNING_POPEN_WAIT_ZERO','retained_tasks':terminal['retained_tasks'],'completed_dynamic_tasks':terminal['completed_dynamic_tasks']})
    for row in rows:
        row.setdefault('retained_tasks',terminal['retained_lineage'].get(row['attempt'],0));row.setdefault('completed_dynamic_tasks',0)
    return rows
def configure(api,plan,c,terminal):
    original_artifact=api.phase_artifact; api._original_phase_artifact=original_artifact
    def artifact(root,path):
        p=Path(path).resolve()
        if p.is_relative_to(s.RESULTS/'execution/dynamic'):return None
        return original_artifact(root,path)
    api.phase_artifact=artifact
    api.read_phase_history=lambda root,bindings,digest:phase_rows(api,root,bindings,digest,plan,c,terminal)
    render=api.render_reports
    def reports(bundle):
        out=render(bundle)
        note=('\n\n## Dynamic execution provenance\n\nOriginal successful V3 records were retained. The first 123 trajectories used one worker; additional static full_002 records and the real bridge smoke are included in the retained inventory. '
              f'The FULL dynamic contract retained {terminal["retained_tasks"]} trajectories and completed {terminal["completed_dynamic_tasks"]} with an outcome-blind resource policy capped at three workers. '
              'All original failed or interrupted attempts remain preserved. External observer finished timestamps are observation cutoffs; earlier actor/actual exit evidence remains NOT_VERIFIED where applicable. '
              'Actual dynamic coordinator and worker exits were observed by their owning Popen objects. No scheduling-invariant or bitwise stochastic output claim is made. The dynamic certificate is separate from old static phase success.\n')
        for name in (*api.REPORT_NAMES,'PAPER3_FINAL_REPLICATION_HANDOFF_DRAFT.md'):
            out[name]=out[name].replace('## Recorded actual phase attempts','## Preserved phase receipts and independently observed dynamic terminal')+note
        for n in s.OWN:out['source/dynamic_delivery/'+n]=(s.HERE/n).read_text(encoding='utf-8')
        for n in (plan['route_proof_path'],plan['_plan_path'],str(Path(plan['record_root'])/'DYNAMIC_FULL_INTEGRITY_CERTIFICATE.json'),
                  str(Path(plan['record_root'])/'FULL_GATE_PUBLICATION.json')):
            out['source/dynamic_delivery/'+Path(n).name]=Path(n).read_text(encoding='utf-8')
        out['source/dynamic_delivery/ADAPTATION_DECLARATION.json']=s.json.dumps({'schema':'paper3-dynamic-delivery-adaptation-v1',
            'original_sources_sha256':s.ORIGINAL,'metadata_only':True,'original_scientific_arithmetic_changed':False,
            'static_completion_fabricated':False,'implementation_sha256':s.source_pins()},indent=2)+'\n'
        return out
    api.render_reports=reports

def publish(plan,c,p,manifest,terminal):
    """All gates pass before publication; failures preserve exclusive evidence."""
    s.verify_plan(plan['_plan_path']);s.closure(p,manifest)
    record=Path(plan['record_root']); stats_exit=s.read(record/'STATISTICS_PROCESS_EXIT.json')
    s.require(type(stats_exit.get('actual_exit_code')) is int and stats_exit['actual_exit_code']==0 and stats_exit.get('automatic_retry') is False,'actual statistics exit absent')
    api=s.load_module(s.BASE/'replication_delivery_env_v3/delivery.py','paper3_dynamic_original_delivery',s.ORIGINAL['replication_delivery_env_v3/delivery.py'])
    configure(api,plan,c,terminal)
    delivery=api.publish_delivery(s.REPO,s.MANIFEST,plan['reviewed_handoff_relative'])
    f=s.load_module(s.BASE/'replication_abrupt_recovery_v1/finalizer.py','paper3_dynamic_original_publication',s.ORIGINAL['replication_abrupt_recovery_v1/finalizer.py'])
    f.PACKAGE_REL=plan['reviewed_handoff_relative'] # Private metadata path only; original function body unchanged.
    checked=f.verify_delivery(s.REPO)
    s.require(checked['_verified_manifest_sha256']==s.sha(s.REPO/plan['reviewed_handoff_relative']/'DELIVERY_MANIFEST.json'),'reviewed delivery changed')
    target=s.safe(s.REPO/plan['final_handoff_relative']);s.require(not target.exists(),'final package exists');target.mkdir(parents=True,exist_ok=False)
    source=s.REPO/plan['reviewed_handoff_relative']; inventory=f.inventory(source)
    for relative,h in inventory.items():f.copy_verified(f.safe(source,relative),f.safe(target,'reviewed_delivery/'+relative),h)
    certificate=s.read(record/'DYNAMIC_FULL_INTEGRITY_CERTIFICATE.json')
    preserved=dict(certificate['evidence_sha256'])
    for path in record.iterdir():
        if path.is_file() and path.name!='finish.json':preserved[str(path)]=s.sha(path)
    f.emit(target/'DYNAMIC_PROVENANCE_INDEX.json',preserved)
    for n,h in s.source_pins().items():f.copy_verified(n,target/'dynamic_route_source'/Path(n).name,h)
    publication=target/'root_publication';publication.mkdir(exist_ok=False)
    draft=source/'PAPER3_FINAL_REPLICATION_HANDOFF_DRAFT.md'; draft_sha=delivery['package_files_sha256'][draft.name]
    def precommit():
        s.verify_plan(plan['_plan_path'])
        for n,h in preserved.items():s.bound(n,h)
        f.verify_delivery(s.REPO)
        s.closure(p,manifest)
        gate=s.read(c['activation_gate_path'])
        s.require(all(not s.process_active(pid) for pid in gate['old_process_ids']),'old owner revived before root publication')
        s.require(not s.process_active(s.read(plan['coordinator_exit_path'])['pid']),'dynamic coordinator still active')
    s.require(plan.get('root_publication_authorized') is True,'root publication authorization absent')
    root_sha=f.publish_root(s.REPO,publication,s.F50,draft,draft_sha,precommit=precommit)
    package_manifest={'schema':'paper3-dynamic-final-package-v1','status':'COMPLETED','manifest_digest':s.MANIFEST,
                      'input_bundle_digest':s.F1,'dynamic_attempt_id':c['attempt_id'],'root_handoff_sha256':root_sha,
                      'previous_root_handoff_sha256':s.F50,'package_files_sha256':f.inventory(target),'static_success_fabricated':False}
    f.emit(target/'FINAL_PACKAGE_MANIFEST.json',package_manifest)
    zip_path=s.safe(s.REPO/plan['zip_relative']); zip_sha=f.make_zip(target,zip_path)
    return {'reviewed_package':str(source),'final_package':str(target),'zip_path':str(zip_path),'zip_sha256':zip_sha,
            'root_handoff_sha256':root_sha,'previous_root_handoff_sha256':s.F50}
