"""Strict PD configuration; seconds, integer bytes and explicit evidence."""
from dataclasses import dataclass
from schemas.dag.v1.io import finite_nonnegative, read_json
from .kv_layout import DTYPES, positive_int


@dataclass(frozen=True)
class PDConfig:
    storage_dtype: str
    capacity_bytes_per_shard: int
    bandwidth_bytes_per_s: float
    latency_s: float
    occupies_gpu: bool
    evidence: str
    legacy_prefill_billing_extra_token: bool = False
    transfer_start_mode: str = "push"

    @classmethod
    def from_dict(cls, data):
        fields = {"schema_version", "storage_dtype", "capacity_bytes_per_shard", "bandwidth_bytes_per_s",
                  "latency_s", "occupies_gpu", "evidence"}
        if not isinstance(data, dict):
            raise ValueError("PD configuration must be an object")
        version = data.get("schema_version")
        if version == "1.0":
            expected = fields
        elif version == "1.1":
            expected = fields | {"legacy_prefill_billing_extra_token"}
        elif version == "1.2":
            expected = fields | {"legacy_prefill_billing_extra_token", "transfer_start_mode"}
        else:
            raise ValueError("unsupported PD configuration version")
        if set(data) != expected:
            raise ValueError("PD configuration fields do not match its version")
        extra_token = data.get("legacy_prefill_billing_extra_token", False)
        if type(extra_token) is not bool:
            raise ValueError("legacy_prefill_billing_extra_token must be boolean")
        transfer_mode = data.get("transfer_start_mode", "push")
        if transfer_mode not in ("push", "decode_pull_candidate"):
            raise ValueError("unsupported PD transfer start mode")
        if data["storage_dtype"] not in DTYPES:
            raise ValueError("unsupported storage dtype; wire dtype must equal storage dtype")
        capacity = positive_int(data["capacity_bytes_per_shard"], "capacity_bytes_per_shard")
        bandwidth = finite_nonnegative(data["bandwidth_bytes_per_s"])
        if bandwidth == 0 or type(data["occupies_gpu"]) is not bool:
            raise ValueError("PD bandwidth must be positive and occupies_gpu must be boolean")
        if not isinstance(data["evidence"], str) or not data["evidence"].strip():
            raise ValueError("PD cost evidence is required")
        latency = finite_nonnegative(data["latency_s"])
        if extra_token and latency != 0:
            raise ValueError("legacy fee parity requires zero fixed latency")
        return cls(data["storage_dtype"], capacity, bandwidth, latency,
                   data["occupies_gpu"], data["evidence"], extra_token, transfer_mode)

    @classmethod
    def load(cls, path):
        return cls.from_dict(read_json(path))


def validate_simulation_config(config):
    """Reject declared layouts the original cluster builder cannot execute faithfully."""
    cluster = config.cluster_config
    replica = cluster.replica_config
    if not 0 < replica.pd_node_ratio < 1:
        raise ValueError("DAG PD requires both Prefill and Decode replicas")
    if str(cluster.global_scheduler_config.get_type()) != "split_wise" or str(cluster.replica_scheduler_config.get_type()) != "split_wise":
        raise ValueError("DAG PD requires Splitwise global and replica schedulers")
    for field, common in (("prefill_tensor_parallel_size", replica.tensor_parallel_size),
                          ("decode_tensor_parallel_size", replica.tensor_parallel_size),
                          ("prefill_num_pipeline_stages", replica.num_pipeline_stages),
                          ("decode_num_pipeline_stages", replica.num_pipeline_stages)):
        if getattr(replica, field) not in (None, common):
            raise ValueError("DAG PD requires homogeneous P/D TP and PP, matching common TP/PP")
    count = cluster.num_replicas * replica.pd_node_ratio
    if count != int(count) or (replica.num_prefill_replicas is not None and replica.num_prefill_replicas != int(count)):
        raise ValueError("PD ratio must produce integral counts consistent with num_prefill_replicas")
