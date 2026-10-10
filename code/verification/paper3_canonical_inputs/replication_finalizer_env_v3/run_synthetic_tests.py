"""Execute only temporary synthetic tests, preserve exact source/test receipt."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
    target=HERE/'SYNTHETIC_TEST_RESULTS_ATTEMPT001.json'
    assert not target.exists(),'independent synthetic proof already exists'
    before={path.name:sha(path) for path in HERE.glob('*.py')}
    started=datetime.now(timezone.utc).isoformat()
    command=[sys.executable,'-I','-S','-B',str(HERE/'test_finalizer.py')]
    result=subprocess.run(command,capture_output=True)
    after={path.name:sha(path) for path in HERE.glob('*.py')}
    assert before==after,'source changed during synthetic tests'
    for name,data in [('SYNTHETIC_STDOUT_ATTEMPT001.log',result.stdout),('SYNTHETIC_STDERR_ATTEMPT001.log',result.stderr)]:
        with (HERE/name).open('xb') as out:out.write(data)
    summary=result.stderr.decode('utf-8',errors='replace')
    count=re.search(r'Ran (\d+) tests',summary);skipped=re.search(r'skipped=(\d+)',summary)
    tests_run=int(count.group(1)) if count else 0;tests_skipped=int(skipped.group(1)) if skipped else 0
    proof={'all_pass':result.returncode==0 and tests_run>0 and tests_skipped==0,'exit_code':result.returncode,'tests_run':tests_run,'tests_skipped':tests_skipped,'started_utc':started,'finished_utc':datetime.now(timezone.utc).isoformat(),'command':command,'implementation_sha256':after,'real_outcomes_read':False,'real_delivery_published':False,'models_generators_or_statistics_executed':False,'stdout_sha256':hashlib.sha256(result.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(result.stderr).hexdigest()}
    with target.open('x',encoding='utf-8') as out:json.dump(proof,out,indent=2);out.write('\n')
    sys.stdout.buffer.write(result.stdout);sys.stderr.buffer.write(result.stderr)
    raise SystemExit(result.returncode)
if __name__=='__main__':main()
