"""Compatibility entry only; original saved-result finalizer main stays byte-identical."""
import importlib.util
from pathlib import Path
path = Path(__file__).with_name('compat_entry.py')
spec = importlib.util.spec_from_file_location('paper3_compat_entry', path)
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
if __name__ == '__main__':
    entry.run('finalizer', Path(__file__).resolve())
