"""Test fixture process: hashes task identities, never imports project/model code."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

root=Path(sys.argv[1]); delay=float(sys.argv[2]); contract=sys.argv[3]
def emit(relative,value):
    path=root/relative;path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.pending')
    with temporary.open('xb') as stream:stream.write((json.dumps(value)+'\n').encode());stream.flush();os.fsync(stream.fileno())
    os.link(temporary,path)
emit('ready.json',{'pid':os.getpid(),'contract_sha256':contract,'synthetic_only':True})
sequence=0
while True:
    sequence+=1;path=root/f'commands/{sequence:06d}.json'
    while not path.exists():time.sleep(.002)
    command=json.loads(path.read_bytes())
    assert command['contract_sha256']==contract
    if command['action']=='STOP':
        emit('finished.json',{'synthetic_only':True,'contract_sha256':contract,'finished_at_idle_boundary':True})
        break
    time.sleep(delay)
    result=hashlib.sha256(command['task_digest'].encode()).hexdigest()
    emit(f'events/{sequence:06d}.done.json',{'claim_id':command['claim_id'],'task_digest':command['task_digest'],
        'task':command['task'],'receipt_sha256':result,'output_hash':result,'contract_sha256':contract,
        'synthetic_only':True})
