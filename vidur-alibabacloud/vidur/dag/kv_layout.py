"""Homogeneous P/D KV shards, with explicit storage and transport units."""
from dataclasses import dataclass
from numbers import Integral

DTYPES = {"float16": 2, "bfloat16": 2, "float32": 4, "fp8": 1, "int8": 1}


def positive_int(value, name):
    if not isinstance(value, Integral) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


@dataclass(frozen=True)
class KVLayout:
    layers: int
    kv_heads: int
    head_dim: int
    tp: int
    pp: int
    dtype: str
    block_size: int

    def __post_init__(self):
        for name in ("layers", "kv_heads", "head_dim", "tp", "pp", "block_size"):
            positive_int(getattr(self, name), name)
        if self.dtype not in DTYPES:
            raise ValueError(f"unsupported KV dtype: {self.dtype}")
        if self.layers % self.pp:
            raise ValueError("layers must divide evenly across PP stages")
        if self.kv_heads % self.tp and self.tp % self.kv_heads:
            raise ValueError("KV heads must shard evenly or replicate evenly across TP ranks")

    @property
    def bytes_per_token_per_shard(self):
        return 2 * (self.layers // self.pp) * max(1, self.kv_heads // self.tp) * self.head_dim * DTYPES[self.dtype]

    def storage(self, tokens):
        positive_int(tokens, "tokens")
        rounded = ((tokens + self.block_size - 1) // self.block_size) * self.block_size
        return rounded * self.bytes_per_token_per_shard

    def wire(self, valid_tokens):
        return positive_int(valid_tokens, "valid_tokens") * self.bytes_per_token_per_shard

    def shards(self, replica_id):
        return tuple(f"gpu:{replica_id}:{stage}:{rank}" for stage in range(self.pp) for rank in range(self.tp))
