"""Minimal authorized extraction/config diagnostic: never calls a generator."""
from __future__ import annotations
import hashlib
import importlib.abc
import importlib.machinery
import importlib
import json
from pathlib import Path
import sys
import traceback
import types

ROOT = Path(__file__).resolve().parent
VERIFIER = ROOT.parent / "verifier_v1"
REPO = ROOT.parents[2]
APPROVED = json.loads((ROOT / "environment.reviewed.json").read_text())
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
bound = {str(p.resolve()).casefold(): sha(p) for p in VERIFIER.rglob("*.py")}
bound[str(Path(__file__).resolve()).casefold()] = sha(__file__)
for root_name, key in (("stdlib_root","stdlib_files_sha256"),("numpy_parent","numpy_files_sha256")):
    for rel,digest in APPROVED[key].items():
        p=Path(APPROVED[root_name])/rel
        if sha(p)!=digest:raise RuntimeError("approved dependency changed")
        bound[str(p.resolve()).casefold()]=digest
for filename,digest in APPROVED["runtime_binary_files_sha256"].items():
    if sha(filename)!=digest:raise RuntimeError("approved runtime binary changed")
    bound[str(Path(filename).resolve()).casefold()]=digest
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self,name,path=None,target=None):
        if name.split(".")[0] in {"core","imported","scripts","torch","pandas","sklearn","verification"}:
            raise RuntimeError("forbidden project/model import")
        for finder in (importlib.machinery.BuiltinImporter,importlib.machinery.FrozenImporter,importlib.machinery.PathFinder):
            spec=finder.find_spec(name,path,target)
            if spec is not None:
                if spec.origin not in (None,"built-in","frozen"):
                    resolved=Path(spec.origin).resolve()
                    if bound.get(str(resolved).casefold())!=sha(resolved):
                        raise RuntimeError("unapproved exact module origin")
                return spec
        return None
sys.meta_path.insert(0,Guard())
sys.path.append(APPROVED["numpy_parent"])
pkg=types.ModuleType("paper3_civ_diagnostic")
pkg.__path__=[str(VERIFIER)]
sys.modules[pkg.__name__]=pkg
module=importlib.import_module("paper3_civ_diagnostic.materialization")
forbidden={"generate_base_centers","simulate_centers","make_scenario_v2","_generate_latent_workload","_generate_clean_metrics","_physical_shift","apply_c3_regime_b","c4_target"}
def trace(frame,event,arg):
    if event=="call" and frame.f_code.co_name in forbidden:
        raise RuntimeError("actual generator/function execution forbidden in minimal diagnostic")
    return trace
sys.settrace(trace)
tag=sys.argv[1]
step="load_pure_runtime"
result={"scope":"ONLY_PURE_DEFINITION_LOADING_AND_CONFIG_RESOLUTION","generator_called":False,"model_called":False}
try:
    pins=json.loads((VERIFIER/"source_pins.json").read_text())["sources"]
    runtime=module.load_pure_runtime(REPO,pins)
    step="_resolved_config"
    config=module._resolved_config(runtime)
    result.update({"status":"PASS","resolved_config_data_seed":config["data_seed"]})
    if tag == "synthetic_rng_before":
        step="synthetic np.random.RandomState(0) constructor, zero draws"
        restricted=module._namespace("paper3_civ_synthetic_rng_probe",runtime["np"])
        exec(compile("probe=np.random.RandomState(0)","<synthetic_numpy_rng_probe>","exec"),restricted)
        result["synthetic_zero_draw_rng_constructor"]="PASS"
    if tag == "synthetic_operations_before":
        restricted=module._namespace("paper3_civ_synthetic_numpy_probe",runtime["np"])
        statements=[
            "rng=np.random.RandomState(0)",
            "a=np.arange(4,dtype=np.float64)",
            "b=np.ones((4,2),dtype=np.float32)",
            "c=np.zeros((4,2),dtype=np.float32)",
            "d=np.clip(a,0.0,1.0)",
            "e=np.sin(a)+np.exp(a)",
            "f=rng.normal(0.0,0.1,size=(4,2))",
            "g=rng.uniform(0.0,1.0,size=4)",
            "h=rng.randint(0,10)",
            "i=rng.choice(['A','B','C'])",
            "j=rng.choice(['tight','medium','loose'],p=[0.2,0.5,0.3])",
            "k=['A','B','C'];rng.shuffle(k)",
            "l=b.astype(np.float32)",
            "m=np.concatenate([b,c],axis=1).astype(np.float32)",
            "n=float(b.mean())",
        ]
        result["synthetic_operations"]=[]
        for statement in statements:
            step=statement
            exec(compile(statement,"<synthetic_numpy_operations_probe>","exec"),restricted)
            result["synthetic_operations"].append({"statement":statement,"status":"PASS"})
    if tag == "capture_implicit_import":
        result["implicit_import_requests"]=[]
        restricted=module._namespace("paper3_civ_synthetic_numpy_probe",runtime["np"])
        def capture(name,globals=None,locals=None,fromlist=(),level=0):
            result["implicit_import_requests"].append({"name":name,"fromlist":list(fromlist or []),"level":level})
            raise RuntimeError("implicit import captured without executing it: "+name)
        restricted["__builtins__"]["__import__"]=capture
        step="synthetic b.mean() with nonexecuting import capture"
        exec(compile("b=np.ones((4,2),dtype=np.float32);n=float(b.mean())","<synthetic_numpy_import_capture>","exec"),restricted)
except Exception as error:
    result.update({"status":"ERROR","failed_step":step,"type":type(error).__name__,"message":str(error),"traceback":traceback.format_exc()})
finally:
    sys.settrace(None)
with(ROOT/f"stage_b_materialization_diagnostic_{tag}.json").open("x",encoding="utf-8")as s:json.dump(result,s,indent=2)
print(json.dumps(result,indent=2))
