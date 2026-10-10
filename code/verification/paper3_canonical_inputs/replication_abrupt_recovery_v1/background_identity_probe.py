"""Harmless read-only check of actual WMI-launched user and parent identity."""
import importlib.util
import json
from pathlib import Path
root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('owned_supervisor_identity_probe', root / 'durable_supervisor.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
value = {'scope': 'Owned stdlib-only identity check; no scientific work or process control.'}
try:
    value.update(windows_user=module.current_user(), parent_image=module.parent_image(), status='PASS')
except BaseException as error:
    value.update(status='FAIL', exception_type=type(error).__name__, message=str(error))
with (root / 'background_identity_probe_001.json').open('x', encoding='utf-8') as stream:
    json.dump(value, stream, indent=2)
