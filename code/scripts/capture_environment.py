from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
environment = {
    "python_executable": sys.executable,
    "python_version": platform.python_version(),
    "platform": platform.platform(),
    "torch_version": torch.__version__,
    "cuda_available": torch.cuda.is_available(),
    "torch_cuda_version": torch.version.cuda,
    "cudnn_version": torch.backends.cudnn.version(),
    "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    "cudnn_deterministic": torch.backends.cudnn.deterministic,
    "cudnn_benchmark": torch.backends.cudnn.benchmark,
}
(ROOT / "audits" / "environment.json").write_text(json.dumps(environment, indent=2), encoding="utf-8")
freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], check=True, capture_output=True, text=True).stdout
(ROOT / "configs" / "requirements_frozen.txt").write_text(freeze, encoding="utf-8")
print(json.dumps(environment, indent=2))
