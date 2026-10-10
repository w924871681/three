"""Authorized Stage A environment/source preflight; no generator or model imports."""
from __future__ import annotations
import hashlib
import importlib.machinery
import json
import os
import platform
import stat
import sys
from pathlib import Path

REPO = Path(r"D:\dt-talk\DT_LIFECYCLE_ESCALATION")
HERE = Path(__file__).resolve().parent

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda:handle.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def safe(path):
    path=Path(path).absolute()
    for p in (path,*path.parents):
        if p.exists() or p.is_symlink():
            info=p.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info,"st_file_attributes",0)&0x400:
                raise RuntimeError(f"reparse path: {p}")
    return path.resolve(strict=True)

def write(name,value):
    with (HERE/name).open("xb") as handle:
        handle.write((json.dumps(value,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode())

if not(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
    raise RuntimeError("require -I -S -B")
if not sys.pycache_prefix or Path(sys.pycache_prefix).exists():
    raise RuntimeError("require unused isolated cache prefix")
pins=json.loads((REPO/"verification/paper3_canonical_inputs/verifier_v1/source_pins.json").read_text())
source={k:sha(safe(REPO/k)) for k in pins["sources"]}
if source!=pins["sources"]:raise RuntimeError("source pins changed")
cfg=json.loads((REPO/"configs/P7_7_FINAL_LIFECYCLE_PROTOCOL.json").read_text())
for name,expected in cfg["source_bindings_sha256"].items():
    if sha(safe(REPO/name))!=expected:raise RuntimeError(f"frozen binding changed: {name}")
protected={}
for relative in ("results/p7_7","artifacts","configs","core","scripts","imported"):
    root=safe(REPO/relative)
    for directory,names,files in os.walk(root,followlinks=False):
        names[:]=sorted(n for n in names if n not in {"__pycache__","node_modules",".venv","venv"})
        for n in names:safe(Path(directory)/n)
        for n in sorted(files):
            path=safe(Path(directory)/n)
            if path.suffix not in {".pyc",".pyo"}:protected[path.relative_to(REPO).as_posix()]=sha(path)
for relative in pins["sources"]:protected[relative]=sha(safe(REPO/relative))
write("original_protected_start_sha256.json",protected)
original_audit=json.loads((REPO/"audits/P7_7_FINAL_HELDOUT_SCIENTIFIC_AUDIT.json").read_text())
bad=[name for name,expected in original_audit["output_hashes"].items() if sha(safe(REPO/name))!=expected]
if bad:raise RuntimeError(f"original output ledger mismatch: {bad}")
write("stage_a_source_integrity_preflight.json",{
    "source_pins_match":True,"frozen_bindings_match":True,"protected_files":len(protected),
    "original_output_ledger_checks":len(original_audit["output_hashes"]),"mismatches":bad,
    "raw_csv_count":len(list((REPO/"results/p7_7/raw").glob("*.csv"))),
    "raw_receipt_count":len(list((REPO/"results/p7_7/raw").glob("*.integrity.json")))})
prefix=safe(Path(sys.executable).parent)
stdlib=safe(prefix/"Lib")
package_parent=safe(stdlib/"site-packages")
standard={}
for directory,names,files in os.walk(stdlib,followlinks=False):
    names[:]=sorted(n for n in names if n not in {"site-packages","__pycache__"})
    for n in names:safe(Path(directory)/n)
    for n in sorted(files):
        path=Path(directory)/n
        if path.suffix.lower() in {".py",".pyd",".dll",".zip"}:standard[path.relative_to(stdlib).as_posix()]=sha(safe(path))
numpy_files={}
for root in (package_parent/"numpy",package_parent/"numpy.libs"):
    if not root.exists():continue
    for directory,names,files in os.walk(safe(root),followlinks=False):
        for n in names:safe(Path(directory)/n)
        for n in sorted(files):
            path=Path(directory)/n
            if path.suffix.lower() in {".py",".pyi",".pyd",".dll"}:numpy_files[path.relative_to(package_parent).as_posix()]=sha(safe(path))
binaries={}
for root in (prefix,prefix/"DLLs"):
    for path in root.iterdir():
        if path.is_file() and path.suffix.lower() in {".dll",".pyd",".exe"}:binaries[str(safe(path))]=sha(path)
bound={str((stdlib/k).resolve()).casefold():v for k,v in standard.items()}
bound.update({str((package_parent/k).resolve()).casefold():v for k,v in numpy_files.items()})
bound.update({k.casefold():v for k,v in binaries.items()})

class Guard:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split(".")[0] in {"torch","pandas","core","scripts","imported","sklearn"}:raise RuntimeError("model/project import forbidden")
        m=importlib.machinery
        spec=m.BuiltinImporter.find_spec(fullname,path,target) or m.FrozenImporter.find_spec(fullname,path,target)
        if spec:return spec
        spec=m.PathFinder.find_spec(fullname,path,target)
        if spec is None:return None
        if not spec.origin:raise RuntimeError(f"unbound namespace: {fullname}")
        resolved=safe(Path(spec.origin));expected=bound.get(str(resolved).casefold())
        if expected is None or sha(resolved)!=expected:raise RuntimeError(f"unbound import: {fullname}: {resolved}")
        return spec

sys.meta_path.insert(0,Guard())
sys.path.append(str(package_parent))
import numpy as np
threads=("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","BLIS_NUM_THREADS","VECLIB_MAXIMUM_THREADS","NUMEXPR_NUM_THREADS","OMP_DYNAMIC","MKL_DYNAMIC","NPY_DISABLE_CPU_FEATURES","OPENBLAS_CORETYPE","MKL_CBWR")
environment={"schema":"paper3-civ-approved-environment-v1","python_executable":str(safe(Path(sys.executable))),
    "python_executable_sha256":sha(sys.executable),"python_version":platform.python_version(),
    "platform":platform.platform(),"byteorder":sys.byteorder,
    "hardware":{"machine":platform.machine(),"processor":platform.processor(),"processor_identifier":os.environ.get("PROCESSOR_IDENTIFIER")},
    "thread_environment":{k:os.environ.get(k) for k in threads},"stdlib_root":str(stdlib),"stdlib_files_sha256":standard,
    "numpy_parent":str(package_parent),"numpy_files_sha256":numpy_files,"numpy_version":np.__version__,
    "numpy_build_configuration":np.__config__.CONFIG,"runtime_binary_files_sha256":binaries,
    "historical_environment_reproduced":False,"authorization_reference":"Researcher explicit unattended Stage A-E authorization, 2026-10-09"}
write("environment.reviewed.json",environment)
print(json.dumps({"status":"SOURCE_ENVIRONMENT_PREFLIGHT_COMPLETED","source_files":len(source),"protected_files":len(protected),
    "stdlib_files":len(standard),"numpy_files":len(numpy_files),"runtime_binaries":len(binaries),"numpy_version":np.__version__,
    "environment_sha256":sha(HERE/"environment.reviewed.json"),"no_generator_or_model_called":True}))
