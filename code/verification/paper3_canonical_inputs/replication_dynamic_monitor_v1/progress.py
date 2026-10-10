import sys,json,hashlib,argparse
parser=argparse.ArgumentParser(description='READ ONLY saved trajectory count, pairing, and runtime ETA; no model/statistical execution')
parser.add_argument('--previous-valid',type=int,required=True)
args=parser.parse_args()
from pathlib import Path
from datetime import datetime,timezone,timedelta
root=Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
results=root/"results/p7_7_integrity_replication_batch20_env_v3"
sys.path.insert(0,str(root/"verification/paper3_canonical_inputs/replication_dynamic_scheduler_v1"))
from frozen_reference import FrozenReference
from integrity import validate_completion,paired_groups
from queue_store import read_json
ref=FrozenReference(results/"provenance_manifest.json")
assert ref.manifest["manifest_digest"]=="7eebe390398395b6ebb1247ba2722b6d5928a65b0c06d039b85eacaa39c359ea"
assert ref.manifest["input_bundle_digest"]=="ac82f95f4db3b1f624e5348cc8535d75ee3edc8d589c08e74d4aa6fa93f5e228"
proofs=[];receipts=[];errors=[];pending=[]
snapshot=sorted((results/"raw").glob("*.integrity.json"))
for path in snapshot:
    try:
        receipt=read_json(path)
        proofs.append(validate_completion(results,receipt["task"],ref.expected(receipt["task"])))
        receipts.append(receipt)
    except (FileNotFoundError,json.JSONDecodeError) as e:
        pending.append({"file":path.name,"error":str(e)})
    except Exception as e:
        errors.append({"file":path.name,"error":type(e).__name__+": "+str(e)})
try:
    pairing=paired_groups(proofs)
except Exception as e:
    pairing={"error":str(e)}
    errors.append({"pairing":str(e)})
now=datetime.now(timezone.utc)
all_times=sorted(datetime.fromisoformat(v["created_utc"]) for v in receipts)
times=sorted(datetime.fromisoformat(v["created_utc"]) for v in receipts if v["attempt_id"]=="A_DYNAMIC_0002")
rates={}
elapsed=(now-times[0]).total_seconds()/60 if times else 0
for mins in (30,60):
    n=sum(t>=now-timedelta(minutes=mins) for t in times)
    stable=elapsed>=mins and n>=5
    rates[str(mins)+"min"]={"valid_dynamic_completed":n,"per_minute":n/mins if stable else None,"remaining_hours":(1200-len(proofs))/(n/mins)/60 if stable else None,"sufficient_actual_saved_window":stable}
rates["dynamic_saved_interval"]={"valid_completed":len(times),"minutes_since_first_saved":elapsed,"per_minute":(len(times)-1)/elapsed if len(times)>=15 and elapsed>=30 else None,"status":"STABLE_WINDOW_AVAILABLE" if len(times)>=15 and elapsed>=30 else "NO_STABLE_DYNAMIC_ETA"}
lineage={}
for v in receipts:lineage[v["attempt_id"]]=lineage.get(v["attempt_id"],0)+1
unreceipted=sorted({p.stem for p in (results/"raw").glob("*.csv")}-{p.name.removesuffix(".integrity.json") for p in snapshot})
checks={
 "root_handoff_unchanged":hashlib.sha256((root/"PAPER3_FINAL_REPLICATION_HANDOFF.md").read_bytes()).hexdigest()=="f50fa7c8e6abd916124d423ad2b5950df2a7c631d02403eaf8e1cc5736f06ee8",
 "manifest_file_sha_unchanged":hashlib.sha256((results/"provenance_manifest.json").read_bytes()).hexdigest()=="c9277ed25b9c4e6df0b2ecfffeeefa3fdaa087ba4f326de828513402d5d20076",
 "model_modules_imported":sorted(x for x in sys.modules if x in ("torch","numpy","pandas","core") or x.startswith("core.")),
 "final_full_gate_exists":(results/"full_experiment_integrity_gate.json").exists(),
}
print(json.dumps({"checked_utc":now.isoformat(),"receipt_snapshot":len(snapshot),"valid":len(proofs),"remaining":1200-len(proofs),"increment_since_previous":len(proofs)-args.previous_valid,"pairing":pairing,"errors":errors,"pending":pending,"latest_saved_utc":all_times[-1].isoformat() if all_times else None,"attempt_lineage":lineage,"unreceipted_csv_names":unreceipted,"rates":rates,"checks":checks},ensure_ascii=False,indent=2))
