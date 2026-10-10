"""Execute only isolated synthetic continuation/finalizer tests; no real control."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime,timezone

HERE=Path(__file__).resolve().parent
OWN=('continuation.py','finalizer.py','test_continuation.py','run_continuation_tests.py')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
    target=HERE/'SYNTHETIC_CONTINUATION_TEST_RESULTS_ATTEMPT001.json';assert not target.exists()
    before={name:sha(HERE/name) for name in OWN};started=datetime.now(timezone.utc).isoformat()
    command=[sys.executable,'-I','-S','-B',str(HERE/'test_continuation.py')]
    result=subprocess.run(command,capture_output=True)
    after={name:sha(HERE/name) for name in OWN};assert before==after
    for name,data in [('CONTINUATION_SYNTHETIC_STDOUT_ATTEMPT001.log',result.stdout),('CONTINUATION_SYNTHETIC_STDERR_ATTEMPT001.log',result.stderr)]:
        with (HERE/name).open('xb') as out:out.write(data)
    summary=result.stderr.decode('utf-8',errors='replace');count=re.search(r'Ran (\d+) tests',summary);skipped=re.search(r'skipped=(\d+)',summary)
    tests_run=int(count.group(1)) if count else 0;tests_skipped=int(skipped.group(1)) if skipped else 0
    failures_match=re.search(r'failures=(\d+)',summary);errors_match=re.search(r'errors=(\d+)',summary)
    failures=int(failures_match.group(1)) if failures_match else 0;errors=int(errors_match.group(1)) if errors_match else 0
    proof={'schema':'paper3-abrupt-recovery-continuation-synthetic-tests-v1','status':'PASS' if result.returncode==0 and tests_run>=102 and tests_skipped==0 else 'FAIL','failures':failures,'errors':errors,'skipped':tests_skipped,'all_pass':result.returncode==0 and tests_run>0 and tests_skipped==0,'exit_code':result.returncode,'tests_run':tests_run,'tests_skipped':tests_skipped,'started_utc':started,'finished_utc':datetime.now(timezone.utc).isoformat(),'command':command,'implementation_sha256':after,'real_outcomes_read':False,'real_delivery_published':False,'models_generators_or_statistics_executed':False,'real_processes_stopped_or_started':False,'stdout_sha256':hashlib.sha256(result.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(result.stderr).hexdigest()}
    with target.open('x',encoding='utf-8') as out:json.dump(proof,out,indent=2);out.write('\n')
    sys.stdout.buffer.write(result.stdout);sys.stderr.buffer.write(result.stderr);raise SystemExit(result.returncode)
if __name__=='__main__':main()
