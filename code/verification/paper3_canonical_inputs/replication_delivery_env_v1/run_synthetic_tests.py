"""Run independent synthetic delivery tests and save exact implementation proof."""
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys
ROOT=pathlib.Path(__file__).resolve().parent
command=[sys.executable,'-I','-S','-B',str(ROOT/'test_delivery.py')]
start=datetime.datetime.now(datetime.timezone.utc).isoformat()
process=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,encoding='utf-8')
with (ROOT/'synthetic_tests_attempt003.stdout.log').open('x',encoding='utf-8') as stream: stream.write(process.stdout)
with (ROOT/'synthetic_tests_attempt003.stderr.log').open('x',encoding='utf-8') as stream: stream.write(process.stderr)
receipt={'all_pass':process.returncode==0,'exit_code':process.returncode,'command':command,
    'started_utc':start,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'real_outcomes_read':False,'models_generators_or_statistics_executed':False,'real_delivery_published':False,
    'implementation_sha256':{path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in ROOT.glob('*.py')},
    'stdout_sha256':hashlib.sha256(process.stdout.encode()).hexdigest(),
    'stderr_sha256':hashlib.sha256(process.stderr.encode()).hexdigest()}
with (ROOT/'SYNTHETIC_TEST_RESULTS_ATTEMPT003.json').open('x',encoding='utf-8') as stream: json.dump(receipt,stream,indent=2)
print(process.stderr)
sys.exit(process.returncode)
