"""Helpers for converting vLLM diagnostic events into Vidur profile buckets.

The profile format predates the fused vLLM implementation.  This module keeps
the conversion explicit: RoPE is folded into the pre-projection bucket, the
combined FlashAttention/KV interval is the phase-specific attention bucket,
and the sampler host interval is treated as an inclusive model-boundary
bucket.  No validation completion time is used here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MappingContract:
    version: str = "v1"
    rope_policy: str = "merge_into_attn_pre_proj"
    attention_policy: str = "combined_interval_to_phase_attention"
    kv_save_policy: str = "zero_when_combined_attention_includes_kv"
    boundary_policy: str = "inclusive_sampler_host_interval"
    residual_policy: str = "fused_norm_bucket_and_zero_add"

    def as_dict(self) -> dict[str, str]:
        return {
            "version": self.version,
            "rope_policy": self.rope_policy,
            "attention_policy": self.attention_policy,
            "kv_save_policy": self.kv_save_policy,
            "boundary_policy": self.boundary_policy,
            "residual_policy": self.residual_policy,
        }


def merge_rope_into_pre_proj(pre_proj_ms: float, rope_ms: float) -> tuple[float, float]:
    """Return schema-compatible pre-projection and explicit-RoPE values."""

    if pre_proj_ms < 0 or rope_ms < 0:
        raise ValueError("profile timings must be non-negative")
    return pre_proj_ms + rope_ms, 0.0


def phase_code(phase: str) -> int:
    if phase == "prefill":
        return 0
    if phase == "decode":
        return 1
    raise ValueError(f"unknown phase: {phase}")
