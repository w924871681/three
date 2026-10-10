"""Authorized Stage E CLI; refuses incomplete experiments or existing output.

Example (only after 1200/240 final integrity PASS):
  python -I -S -B -X pycache_prefix=<new-root>/never_created_pycache \
    run_statistics.py --expected-manifest-digest <actual manifest_digest>
TEMP/TMP/TORCH_HOME/CUDA_CACHE_PATH must already point inside the new root.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import types
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-manifest-digest",required=True)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    package_name = "paper3_authorized_statistics_env_v2"
    package = types.ModuleType(package_name)
    package.__path__ = [str(folder)]
    sys.modules[package_name] = package
    path = folder/"statistics.py"
    spec = importlib.util.spec_from_file_location(package_name+".statistics",path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    receipt = module.run_statistics(module.REPOSITORY,module.RESULTS_ROOT,
        expected_manifest_digest=args.expected_manifest_digest)
    print(json.dumps(receipt,sort_keys=True),flush=True)


if __name__=="__main__": main()
