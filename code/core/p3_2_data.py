from __future__ import annotations

import numpy as np

from .common import array_digest
from .data import BaseCenter, _logit, _physical_shift, _sigmoid, feature_matrix
from .protocol import CausalTimeline


ONSET_RAW_INDEX = 1400 + 8 * 640


def apply_c3_regime_b(base: BaseCenter, definition: dict) -> tuple[np.ndarray, np.ndarray]:
    """Replace the telemetry transfer function without changing the latent target.

    This is a direct joint-regime construction, not interpolation between model
    predictions.  Values and their masks move together under a fixed channel
    remapping; observed values then receive a fixed monotone calibration map.
    """

    permutation = np.asarray(definition["channel_permutation"], dtype=int)
    slopes = np.asarray(definition["logit_slopes"], dtype=np.float64)
    biases = np.asarray(definition["logit_biases"], dtype=np.float64)
    if sorted(permutation.tolist()) != list(range(12)):
        raise ValueError("C3 channel_permutation must be a permutation of 0..11")
    if slopes.shape != (12,) or biases.shape != (12,) or np.any(slopes <= 0):
        raise ValueError("C3 calibration vectors must have 12 entries and positive slopes")

    values = base.x[:, :12][:, permutation].astype(np.float64)
    masks = base.x[:, 12:24][:, permutation].astype(np.float32)
    calibrated = _sigmoid(_logit(values) * slopes[None, :] + biases[None, :])
    calibrated = (calibrated * masks).astype(np.float32)
    target = base.y.copy()
    if "response_orientation" in definition:
        orientation = int(definition["response_orientation"])
        if orientation != -1:
            raise ValueError("C3 alternate response orientation must be -1")
        latent = _logit(base.y).astype(np.float64)
        center = float(base.metadata["base_logit"])
        target = _sigmoid(center + orientation * (latent - center)).astype(np.float32)
    elif "load_feedback" in definition:
        feedback = definition["load_feedback"]
        lag = int(feedback["lag"])
        strength = float(feedback["strength"])
        slope = float(feedback["slope"])
        if lag <= 0 or strength < 0 or slope <= 0:
            raise ValueError("C3 load feedback parameters must be causal and nonnegative")
        latent = _logit(base.y).astype(np.float64)
        change = np.zeros_like(latent)
        change[lag:] = latent[lag:] - latent[:-lag]
        target = _sigmoid(latent + strength * np.tanh(slope * change)).astype(np.float32)
    return np.concatenate([calibrated, masks], axis=1), target


def c4_target(base: BaseCenter, definition: dict) -> np.ndarray:
    """Generate a nonlinear multi-lag target directly from the latent process."""

    lag1, lag2, lag3, lag4, lag5 = [int(value) for value in definition["lags"]]
    w1, w2, w3 = [float(value) for value in definition["linear_weights"]]
    interaction_weight = float(definition["interaction_weight"])
    interaction_scale = float(definition["interaction_scale"])
    max_lag = max(lag1, lag2, lag3, lag4, lag5)

    latent = _logit(base.y).astype(np.float64)
    center = float(base.metadata["base_logit"])
    residual = latent - center
    generated = latent.copy()
    for index in range(max_lag, len(latent)):
        generated[index] = (
            center
            + w1 * residual[index - lag1]
            + w2 * residual[index - lag2]
            + w3 * residual[index - lag3]
            + interaction_weight
            * np.tanh(
                interaction_scale
                * residual[index - lag4]
                * residual[index - lag5]
            )
        )
    return _sigmoid(generated).astype(np.float32)


def source_regime(base: BaseCenter, regime: str, config: dict) -> tuple[np.ndarray, np.ndarray]:
    if regime == "C3_B":
        return apply_c3_regime_b(base, config["c3_regime_b"])
    if regime == "C4_C":
        return base.x.copy(), c4_target(base, config["c4_regime_c"])
    if regime == "C0_A":
        return base.x.copy(), base.y.copy()
    raise ValueError(f"unknown source regime: {regime}")


def make_scenario_v2(base: BaseCenter, scenario: str, config: dict) -> tuple[np.ndarray, np.ndarray, dict]:
    revision = config["generator_revision"]
    metadata = {
        "scenario": scenario,
        "onset_raw_index": ONSET_RAW_INDEX,
        "generator_revision": revision,
        "prediction_output_blending": False,
    }
    if scenario == "C0":
        x, y = base.x.copy(), base.y.copy()
        metadata["definition"] = "stationary native source regime A"
    elif scenario == "C1":
        index = np.arange(len(base.y))
        shift = 0.8 * np.clip((index - ONSET_RAW_INDEX) / (8 * 640), 0, 1)
        x, y = _physical_shift(base, shift)
        metadata["definition"] = "within-family gradual logit and metric shift"
    elif scenario == "C3":
        replacement_x, replacement_y = apply_c3_regime_b(base, config["c3_regime_b"])
        x, y = base.x.copy(), base.y.copy()
        x[ONSET_RAW_INDEX:] = replacement_x[ONSET_RAW_INDEX:]
        y[ONSET_RAW_INDEX:] = replacement_y[ONSET_RAW_INDEX:]
        metadata.update(
            {
                "definition": "direct same-architecture source-domain A-to-B replacement",
                "mechanism": config["c3_regime_b"]["mechanism"],
                "matched_identity": "p3v2_a57_regime_b",
                "target_unchanged_by_design": not any(
                    key in config["c3_regime_b"]
                    for key in ("load_feedback", "response_orientation")
                ),
                "scientific_rationale": (
                    "a source replacement reverses the centered load-to-risk "
                    "response orientation without altering the temporal innovation "
                    "process; telemetry channel semantics change as prescribed"
                    if "response_orientation" in config["c3_regime_b"]
                    else
                    "a source replacement changes telemetry channel semantics and "
                    "calibration; the new source also has a fixed, causal "
                    "load-feedback response within the same GRU model family"
                    if "load_feedback" in config["c3_regime_b"]
                    else "a machine/source replacement can preserve the latent workload "
                    "while changing telemetry channel semantics and calibration"
                ),
            }
        )
    elif scenario == "C4":
        replacement_y = c4_target(base, config["c4_regime_c"])
        x, y = base.x.copy(), base.y.copy()
        y[ONSET_RAW_INDEX:] = replacement_y[ONSET_RAW_INDEX:]
        metadata.update(
            {
                "definition": "direct nonlinear multi-lag dependency replacement",
                "mechanism": config["c4_regime_c"]["mechanism"],
                "matched_identity": "p3v2_a46_regime_c",
                "same_regime_architecture_control": "p3v2_a57_regime_c_control",
                "target_unchanged_by_design": False,
                "scientific_rationale": (
                    "the post-shift target depends on a fixed nonlinear interaction "
                    "of multiple causal lags within the TCN receptive field"
                ),
            }
        )
    else:
        raise ValueError(f"P3.2 scenario is not prespecified: {scenario}")
    return x.astype(np.float32), y.astype(np.float32), metadata


def timeline_for_v2(base: BaseCenter, scenario: str, config: dict) -> tuple[CausalTimeline, dict]:
    x, y, metadata = make_scenario_v2(base, scenario, config)
    return CausalTimeline(feature_matrix(x, base.dt), y, base.ts, scenario, base.center_id), metadata


def scenario_hash_v2(base: BaseCenter, scenario: str, config: dict) -> str:
    x, y, _ = make_scenario_v2(base, scenario, config)
    return array_digest(x, y, base.ts)


def target_structure(y: np.ndarray, onset: int = ONSET_RAW_INDEX) -> dict:
    values = np.asarray(y[onset:], dtype=np.float64)
    centered = values - values.mean()
    spectrum = np.abs(np.fft.rfft(centered)) ** 2
    if len(spectrum) > 1 and float(spectrum[1:].sum()) > 0:
        peak_index = int(np.argmax(spectrum[1:]) + 1)
        peak_fraction = float(spectrum[peak_index] / spectrum[1:].sum())
        peak_frequency = float(peak_index / len(values))
        peak_period = float(1.0 / peak_frequency)
        probability = spectrum[1:] / spectrum[1:].sum()
        spectral_entropy = float(
            -(probability * np.log(probability + 1e-15)).sum()
            / np.log(max(2, len(probability)))
        )
    else:
        peak_fraction = 0.0
        peak_frequency = 0.0
        peak_period = float("inf")
        spectral_entropy = 0.0

    result = {
        "mean": float(values.mean()),
        "std": float(values.std()),
        "range": float(np.ptp(values)),
        "adjacent_rmse": float(np.sqrt(np.mean(np.diff(values) ** 2))),
        "spectral_peak_frequency": peak_frequency,
        "spectral_peak_period": peak_period,
        "spectral_peak_power_fraction": peak_fraction,
        "spectral_entropy": spectral_entropy,
    }
    for lag in (1, 4, 8, 12, 16, 32, 48, 64):
        result[f"acf_lag_{lag}"] = float(np.corrcoef(values[lag:], values[:-lag])[0, 1])
    return result
