from dataclasses import replace
import json
from pathlib import Path

import pytest

from schemas.dag.v1.io import read_json
from vidur.dag.serialization import graph_from_dict, graph_to_dict, load_graph, snapshot_graph

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/dag/v1"


@pytest.mark.parametrize("name", ["serial", "fork_join", "resource_contention"])
def test_round_trip(name):
    source = read_json(FIXTURES / f"{name}.graph.json")
    for task in source["tasks"]:
        task.setdefault("metadata", {})
    assert graph_to_dict(graph_from_dict(source)) == source


@pytest.mark.parametrize("path", sorted((FIXTURES / "invalid").glob("*.json")), ids=lambda p: p.stem)
def test_invalid_graphs_raise_value_error(path):
    with pytest.raises(ValueError):
        load_graph(path)


def test_snapshot_copies_mutable_metadata():
    graph = load_graph(FIXTURES / "serial.graph.json")
    metadata = {"nested": [1]}
    graph = replace(graph, tasks=(replace(graph.tasks[0], metadata=metadata), *graph.tasks[1:]))
    snapshot = snapshot_graph(graph)
    metadata["nested"].append(2)
    assert snapshot.tasks[0].metadata == {"nested": [1]}


@pytest.mark.parametrize("value", [True, "3", -1, float("inf"), float("nan")])
def test_dataclass_values_are_validated(value):
    graph = load_graph(FIXTURES / "serial.graph.json")
    graph = replace(graph, tasks=(replace(graph.tasks[0], cost=replace(graph.tasks[0].cost, duration_s=value)), *graph.tasks[1:]))
    with pytest.raises(ValueError):
        snapshot_graph(graph)


def test_duplicate_json_keys_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"graph_id":"one","graph_id":"two"}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        read_json(path)


def test_metadata_overflow_rejected():
    data = read_json(FIXTURES / "serial.graph.json")
    data["tasks"][0]["metadata"] = json.loads('{"value": 1e999}')
    with pytest.raises(ValueError):
        graph_from_dict(data)
