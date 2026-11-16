import pytest
from vidur.dag.kv_layout import KVLayout
from vidur.dag.pd_lifecycle import KVTransactions, Migration
from vidur.dag.resources import CapacityResourceManager, ResourceCapacity


def transactions(capacity=64):
    layout = KVLayout(1, 1, 1, 2, 1, "float16", 1)
    manager = CapacityResourceManager({"kv:"+gpu: ResourceCapacity(capacity, "bytes")
                                      for gpu in layout.shards(0)})
    return KVTransactions(manager, layout)


def test_reserve_commit_pin_release_once():
    tx = transactions()
    handles = tx.reserve("r", 0, 32, "source", 0)
    tx.commit("r", handles, "source", 0)
    m = Migration("r", 0, 1, 32, 16, source_handles=handles)
    tx.pin(m, 1)
    with pytest.raises(RuntimeError, match="pinned"):
        tx.manager.release(handles[0], 1)
    assert all(v["used"] == 32 for v in tx.manager.usage_snapshot().values())
    tx.unpin(m, 2)
    tx.release("r", handles, 2)
    assert handles == [] and not m.pins
    assert all(v["used"] == 0 for v in tx.manager.usage_snapshot().values())


def test_partial_reservation_rolls_back():
    tx = transactions()
    last = tx.layout.shards(0)[-1]
    blocker = tx.manager.reserve(("external", "owner"), "kv:"+last, 64)
    assert tx.reserve("r", 0, 32, "destination", 1) is None
    values = list(tx.manager.usage_snapshot().values())
    assert [v["used"] for v in values] == [0, 64]
    tx.manager.release(blocker, 2)
    handles = tx.reserve("r", 0, 32, "destination", 2)
    tx.release("r", handles, 3)
    assert all(v["used"] == 0 for v in tx.manager.usage_snapshot().values())


def test_commit_does_not_charge_capacity_again():
    tx = transactions()
    handles = tx.reserve("r", 0, 32, "destination", 0)
    before = tx.manager.usage_snapshot()
    tx.commit("r", handles, "destination", 1)
    assert before == tx.manager.usage_snapshot()
    with pytest.raises(RuntimeError, match="already been committed"):
        tx.commit("r", handles, "destination", 1)
    tx.release("r", handles, 2)
