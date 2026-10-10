from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import torch

from imported.msa_dti.space.enumerator import enumerate_A_base
from imported.msa_dti.space.models import build_model
from imported.msa_dti.space.profile import profile_arch
from imported.ravm_dt.main_cfg import MainCfg

from .common import ROOT, sha256_file, write_json
from .data import feature_matrix, full_windows, generate_base_centers
from .models import DEVICE, ModelIdentity, build_identity_bank
from .p3_2_data import source_regime


def _source_arrays(base, regime: str, config: dict) -> tuple[np.ndarray, np.ndarray]:
    raw_x, y = source_regime(base, regime, config)
    windows_x, target_indices = full_windows(raw_x, base.dt, length=config["window_length"])
    targets = y[target_indices, None].astype(np.float32)
    train = target_indices < int(config["source_pair"]["train_target_end"])
    return windows_x[train], targets[train]


def _regime_digest(bases, regime: str, config: dict) -> str:
    digest = hashlib.sha256()
    for base in bases:
        raw_x, y = source_regime(base, regime, config)
        for value in (raw_x, y, base.ts):
            array = np.ascontiguousarray(value)
            digest.update(str(array.shape).encode())
            digest.update(array.dtype.str.encode())
            digest.update(array.tobytes())
    return digest.hexdigest()


@torch.no_grad()
def _validation_mse(model, bases, regime: str, config: dict) -> float:
    model.eval()
    squared_sum = 0.0
    count = 0
    start = int(config["source_pair"]["validation_target_start"])
    length = int(config["window_length"])
    for base in bases:
        raw_x, y = source_regime(base, regime, config)
        features = feature_matrix(raw_x, base.dt)
        target_indices = np.arange(start, len(y), dtype=int)
        for left in range(0, len(target_indices), 256):
            ids = target_indices[left : left + 256]
            x = np.stack([features[index - length : index] for index in ids])
            tx = torch.as_tensor(x, dtype=torch.float32, device=DEVICE)
            ty = torch.as_tensor(y[ids, None], dtype=torch.float32, device=DEVICE)
            error = model(tx) - ty
            squared_sum += float(error.square().sum())
            count += int(error.numel())
    return squared_sum / count


def train_source_assets(config: dict) -> dict:
    output_dir = ROOT / "artifacts" / "p3_2_source_bank"
    if config["generator_revision"] != "p3_mismatch_v2_r1":
        output_dir = output_dir / config["generator_revision"]
    manifest_path = output_dir / "source_training_manifest.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("generator_revision") != config["generator_revision"]:
            raise RuntimeError("source-bank manifest revision differs from protocol")
        for item in manifest["assets"]:
            path = ROOT / item["checkpoint"]
            if not path.exists() or sha256_file(path) != item["checkpoint_sha256"]:
                raise RuntimeError(f"existing P3.2 source asset failed hash validation: {path}")
        return manifest

    source = config["source_pair"]
    source_ids = [int(value) for value in source["source_centers"]]
    forbidden = (
        set(config["design_centers"])
        | set(config["fresh_development_centers"])
        | set(config["calibration_centers_forbidden"])
        | set(config["heldout_centers_forbidden"])
    )
    if set(source_ids) & forbidden:
        raise AssertionError("source centers overlap a target-side pool")
    bases = generate_base_centers(
        source_ids,
        data_seed=int(source["source_data_seed"]),
        n_history=int(source["source_n_history"]),
    )
    specs = enumerate_A_base(MainCfg().arch)
    assets = []
    regime_cache: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {}
    started_all = time.perf_counter()

    for asset in source["assets"]:
        identity_id = str(asset["identity_id"])
        arch_index = int(asset["architecture_index"])
        regime = str(asset["regime"])
        seed = int(asset["seed"])
        checkpoint = output_dir / f"{identity_id}.pt"
        if checkpoint.exists():
            raise FileExistsError(f"refusing to overwrite unmanifested source asset: {checkpoint}")

        torch.manual_seed(seed)
        if DEVICE.type == "cuda":
            torch.cuda.manual_seed_all(seed)
        model = build_model(specs[arch_index], input_dim=25, H=1, L=96, device=str(DEVICE))
        optimizer = torch.optim.Adam(
            model.parameters(),
            lr=float(source["learning_rate"]),
            weight_decay=float(source["weight_decay"]),
        )
        asset_started = time.perf_counter()
        epochs = int(source["epochs"])
        batch_size = int(source["batch_size"])
        last_epoch_loss = float("nan")
        if regime not in regime_cache:
            regime_cache[regime] = [_source_arrays(base, regime, config) for base in bases]
        training_arrays = regime_cache[regime]

        for epoch in range(epochs):
            model.train()
            rng = np.random.default_rng(np.random.SeedSequence([seed, epoch]))
            center_order = rng.permutation(len(bases))
            running = 0.0
            samples = 0
            for center_position in center_order:
                x, y = training_arrays[int(center_position)]
                order = rng.permutation(len(x))
                for left in range(0, len(order), batch_size):
                    ids = order[left : left + batch_size]
                    tx = torch.as_tensor(x[ids], dtype=torch.float32, device=DEVICE)
                    ty = torch.as_tensor(y[ids], dtype=torch.float32, device=DEVICE)
                    optimizer.zero_grad(set_to_none=True)
                    loss = torch.nn.functional.mse_loss(model(tx), ty)
                    if not torch.isfinite(loss):
                        raise FloatingPointError(f"non-finite source loss for {identity_id}")
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()
                    running += float(loss.detach()) * len(ids)
                    samples += len(ids)
            last_epoch_loss = running / samples
            if (epoch + 1) % 10 == 0 or epoch == 0:
                print(
                    f"[P3.2 source] {identity_id} epoch={epoch + 1}/{epochs} "
                    f"train_mse={last_epoch_loss:.8f}",
                    flush=True,
                )

        if DEVICE.type == "cuda":
            torch.cuda.synchronize()
        validation_mse = _validation_mse(model, bases, regime, config)
        torch.save(model.state_dict(), checkpoint)
        params, operations = profile_arch(specs[arch_index], L=96, input_dim=25, H=1, device="cpu")
        assets.append(
            {
                "identity_id": identity_id,
                "architecture_index": arch_index,
                "architecture": specs[arch_index].arch_key,
                "family": specs[arch_index].family,
                "source_initialization_id": f"{regime.lower()}_seed_{seed}",
                "regime": regime,
                "seed": seed,
                "checkpoint": str(checkpoint.relative_to(ROOT)).replace("\\", "/"),
                "checkpoint_sha256": sha256_file(checkpoint),
                "source_regime_sha256": _regime_digest(bases, regime, config),
                "parameter_count": int(params),
                "operation_count": int(operations),
                "last_epoch_train_mse": last_epoch_loss,
                "source_validation_mse": validation_mse,
                "training_seconds": time.perf_counter() - asset_started,
            }
        )

    incumbent = next(item for item in build_identity_bank() if item.identity_id == "msa_a57_pt")
    manifest = {
        "schema": "dt-lifecycle-escalation-p3.2-source-bank-v1",
        "generator_revision": config["generator_revision"],
        "source_centers": source_ids,
        "source_data_seed": source["source_data_seed"],
        "source_n_history": source["source_n_history"],
        "target_side_pools_used": False,
        "calibration_used": False,
        "heldout_used": False,
        "training_recipe": {
            key: source[key]
            for key in ("epochs", "optimizer", "loss", "learning_rate", "batch_size", "weight_decay")
        },
        "native_incumbent": {
            **incumbent.to_dict(),
            "upstream_source_manifest": "D:/dt-talk/repository/outputs/shared.evaluation_external_d2904_t2904/source_assets/source_assets_manifest.json",
            "upstream_source_centers": source_ids,
            "upstream_source_data_seed": source["source_data_seed"],
            "source_regime": "C0_A_native",
        },
        "legacy_medet_provenance_finding": (
            "msa_a57_medet and msa_a57_pt used the same upstream source centers; "
            "their distinction is training procedure, not a documented source-domain pair"
        ),
        "assets": assets,
        "total_training_seconds": time.perf_counter() - started_all,
    }
    write_json(manifest_path, manifest)
    return manifest


def build_p3_2_identity_bank(source_manifest: dict) -> list[ModelIdentity]:
    identities = build_identity_bank()
    for asset in source_manifest["assets"]:
        identities.append(
            ModelIdentity(
                identity_id=asset["identity_id"],
                architecture_index=int(asset["architecture_index"]),
                architecture=asset["architecture"],
                family=asset["family"],
                source_initialization_id=asset["source_initialization_id"],
                checkpoint=asset["checkpoint"],
                checkpoint_sha256=asset["checkpoint_sha256"],
                parameter_count=int(asset["parameter_count"]),
                operation_count=int(asset["operation_count"]),
            )
        )
    if len({item.identity_id for item in identities}) != len(identities):
        raise AssertionError("duplicate identity_id in P3.2 bank")
    return identities
