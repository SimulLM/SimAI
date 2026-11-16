import pytest
from vidur.dag.kv_layout import KVLayout
from vidur.dag.pd import PDConfig


def config(**changes):
    return dict(schema_version="1.0", storage_dtype="float16", capacity_bytes_per_shard=1000000000,
                bandwidth_bytes_per_s=1000000, latency_s=0, occupies_gpu=False,
                evidence="synthetic fixture", **changes)


@pytest.mark.parametrize("heads,tp,per_rank_heads", [(8, 2, 4), (2, 4, 1), (1, 8, 1)])
def test_sharding_and_replication(heads, tp, per_rank_heads):
    layout = KVLayout(8, heads, 16, tp, 2, "float16", 4)
    assert layout.bytes_per_token_per_shard == 2 * 4 * per_rank_heads * 16 * 2
    assert layout.storage(5) == 8 * layout.bytes_per_token_per_shard
    assert layout.wire(5) == 5 * layout.bytes_per_token_per_shard
    assert len(layout.shards(1)) == tp * 2


@pytest.mark.parametrize("kwargs", [dict(dtype="unknown"), dict(tp=3), dict(pp=3), dict(block_size=True)])
def test_invalid_layout(kwargs):
    data = dict(layers=8, kv_heads=8, head_dim=16, tp=1, pp=1, dtype="float16", block_size=4)
    with pytest.raises(ValueError):
        KVLayout(**dict(data, **kwargs))


@pytest.mark.parametrize("key,value", [("capacity_bytes_per_shard", 0), ("capacity_bytes_per_shard", True),
    ("bandwidth_bytes_per_s", float("inf")), ("latency_s", -1), ("occupies_gpu", 1),
    ("storage_dtype", "guess"), ("evidence", "")])
def test_invalid_config(key, value):
    data = config()
    data[key] = value
    with pytest.raises(ValueError):
        PDConfig.from_dict(data)


def test_config_rejects_unknown_fields():
    data = config()
    assert PDConfig.from_dict(data).bandwidth_bytes_per_s == 1000000
    with pytest.raises(ValueError):
        PDConfig.from_dict(dict(data, wire_dtype="fp8"))


@pytest.mark.parametrize("field,value", [("pd_node_ratio", 1), ("prefill_tensor_parallel_size", 2),
    ("decode_num_pipeline_stages", 2), ("num_prefill_replicas", 2)])
def test_unsupported_simulation_config_rejected(field, value):
    from types import SimpleNamespace as NS
    from vidur.dag.pd import validate_simulation_config
    replica = NS(pd_node_ratio=.5, tensor_parallel_size=1, num_pipeline_stages=1,
                 prefill_tensor_parallel_size=None, decode_tensor_parallel_size=None,
                 prefill_num_pipeline_stages=None, decode_num_pipeline_stages=None, num_prefill_replicas=None)
    cluster = NS(replica_config=replica, num_replicas=2,
                 global_scheduler_config=NS(get_type=lambda: "split_wise"),
                 replica_scheduler_config=NS(get_type=lambda: "split_wise"))
    validate_simulation_config(NS(cluster_config=cluster))
    setattr(replica, field, value)
    with pytest.raises(ValueError):
        validate_simulation_config(NS(cluster_config=cluster))
