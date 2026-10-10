from __future__ import annotations

import copy
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import torch
from torch import nn

from imported.msa_dti.space.enumerator import enumerate_A_base
from imported.msa_dti.space.models import build_model
from imported.msa_dti.space.profile import profile_arch
from imported.ravm_dt.main_cfg import MainCfg

from .common import ROOT, canonical_hash, sha256_file


DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
torch.set_num_threads(2)
torch.backends.cudnn.benchmark = False
torch.backends.cudnn.deterministic = True


@dataclass(frozen=True)
class ModelIdentity:
    identity_id: str
    architecture_index: int
    architecture: str
    family: str
    source_initialization_id: str
    checkpoint: str
    checkpoint_sha256: str
    parameter_count: int
    operation_count: int

    def to_dict(self) -> dict:
        return asdict(self)


class RoleBatch(tuple):
    def __new__(cls, x: torch.Tensor, y: torch.Tensor, role: str):
        obj = super().__new__(cls, (x, y))
        obj.role = role
        return obj


def state_hash(model: nn.Module) -> str:
    h = hashlib.sha256()
    for name, tensor in model.state_dict().items():
        h.update(name.encode())
        h.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def _arch_specs():
    return enumerate_A_base(MainCfg().arch)


def build_identity_bank() -> list[ModelIdentity]:
    specs = _arch_specs()
    bank_dir = ROOT / "imported" / "msa_dti" / "bank"
    entries = [
        ("msa_a1_pt", 1, "pt_seed_3006", "formal_h1_a1.pt"),
        ("msa_a6_pt", 6, "pt_seed_3011", "formal_h1_a6.pt"),
        ("msa_a46_pt", 46, "pt_seed_3051", "formal_h1_a46.pt"),
        ("msa_a55_pt", 55, "pt_seed_3060", "formal_h1_a55.pt"),
        ("msa_a56_pt", 56, "pt_seed_3061", "formal_h1_a56.pt"),
        ("msa_a57_pt", 57, "pt_seed_3062", "formal_h1_a57.pt"),
        ("msa_a62_pt", 62, "pt_seed_3067", "formal_h1_a62.pt"),
        ("msa_a57_medet", 57, "medet_source_meta_init", "medet_style_h1_a57.pt"),
    ]
    result = []
    for identity_id, index, init_id, filename in entries:
        spec = specs[index]
        params, operations = profile_arch(spec, L=96, input_dim=25, H=1, device="cpu")
        checkpoint = bank_dir / filename
        result.append(
            ModelIdentity(
                identity_id=identity_id,
                architecture_index=index,
                architecture=spec.arch_key,
                family=spec.family,
                source_initialization_id=init_id,
                checkpoint=str(checkpoint.relative_to(ROOT)).replace("\\", "/"),
                checkpoint_sha256=sha256_file(checkpoint),
                parameter_count=params,
                operation_count=operations,
            )
        )
    return result


def bank_hash(identities: Iterable[ModelIdentity]) -> str:
    return canonical_hash([identity.to_dict() for identity in identities])


def load_identity(identity: ModelIdentity) -> nn.Module:
    spec = _arch_specs()[identity.architecture_index]
    model = build_model(spec, input_dim=25, H=1, L=96, device=str(DEVICE))
    state = torch.load(ROOT / identity.checkpoint, map_location=DEVICE, weights_only=True)
    model.load_state_dict(state)
    if hasattr(model, "rnn"):
        model.rnn.flatten_parameters()
    return model


def to_batch(x: np.ndarray, y: np.ndarray, role: str) -> RoleBatch:
    return RoleBatch(
        torch.as_tensor(x, dtype=torch.float32, device=DEVICE),
        torch.as_tensor(y, dtype=torch.float32, device=DEVICE),
        role,
    )


def adapt(parent: nn.Module, batch: RoleBatch, steps: int, seed: int) -> nn.Module:
    if batch.role not in {"update", "warmup"}:
        raise AssertionError(f"gradient update forbidden for role={batch.role}")
    model = copy.deepcopy(parent)
    if hasattr(model, "rnn"):
        model.rnn.flatten_parameters()
    model.train()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
    rng = np.random.default_rng(seed)
    x, y = batch
    for _ in range(int(steps)):
        ids = torch.as_tensor(rng.integers(len(x), size=min(64, len(x))), device=DEVICE)
        optimizer.zero_grad(set_to_none=True)
        loss = nn.functional.mse_loss(model(x[ids]), y[ids])
        if not torch.isfinite(loss):
            raise FloatingPointError("non-finite adaptation loss")
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
    return model


@torch.no_grad()
def evaluate(model: nn.Module, batch: RoleBatch) -> tuple[float, float]:
    model.eval()
    x, y = batch
    predictions = torch.cat([model(x[i : i + 256]) for i in range(0, len(x), 256)])
    return float((predictions - y).square().mean()), float((predictions - y).abs().mean())


@torch.no_grad()
def predict(model: nn.Module, x: np.ndarray) -> np.ndarray:
    model.eval()
    tx = torch.as_tensor(x, dtype=torch.float32, device=DEVICE)
    values = torch.cat([model(tx[i : i + 256]) for i in range(0, len(tx), 256)])
    return values[:, 0].detach().cpu().numpy()


def feasible(identity: ModelIdentity, limits: dict) -> bool:
    return identity.parameter_count <= limits["parameters"] and identity.operation_count <= limits["operations"]
