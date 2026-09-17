"""Tests for `merge_layers`."""
from __future__ import annotations

import copy
from typing import Any

import pytest

from lib_python_config.merge import merge_layers

# --- R5: deep-merge semantics ------------------------------------------------


def test_merge_layers_deep_merges_replacing_lists() -> None:
    layers = [
        {"a": {"x": 1, "y": 1}, "l": [1]},
        {"a": {"y": 2, "z": None}, "l": [2]},
    ]

    result = merge_layers(layers)

    assert result == {"a": {"x": 1, "y": 2}, "l": [2]}


def test_merge_layers_appends_lists() -> None:
    layers = [
        {"a": {"x": 1, "y": 1}, "l": [1]},
        {"a": {"y": 2, "z": None}, "l": [2]},
    ]

    result = merge_layers(layers, list_strategy="append")

    assert result == {"a": {"x": 1, "y": 2}, "l": [1, 2]}


@pytest.mark.parametrize(
    "first_layer",
    [
        {"k": 1},
        {"k": [1, 2]},
        {"k": {"nested": 1}},
        {},
    ],
    ids=["scalar", "list", "mapping", "absent"],
)
def test_merge_layers_later_none_deletes_regardless_of_prior_type(
    first_layer: dict[str, Any],
) -> None:
    result = merge_layers([first_layer, {"k": None}])

    assert "k" not in result


def test_merge_layers_keeps_none_in_first_layer() -> None:
    assert merge_layers([{"a": None}]) == {"a": None}

    x = {"a": None, "b": {"c": None}, "l": [1, 2]}
    result = merge_layers([x])

    assert result == x
    # The single-layer path must deep-copy, not alias, the input: neither
    # the result mapping itself nor any nested mutable container inside it
    # may be the same object as the corresponding container in `x`.
    assert result is not x
    assert result["b"] is not x["b"]
    assert result["l"] is not x["l"]

    # Mutating the result must not affect the original input.
    result["b"]["c"] = "changed"
    result["l"].append(999)

    assert x == {"a": None, "b": {"c": None}, "l": [1, 2]}


def test_merge_layers_mapping_wholesale_replace_keeps_nested_none_literal() -> None:
    # acc["a"] is a scalar (not a Mapping), so the later mapping replaces it
    # wholesale (rule 4) rather than recursing (rule 2) — its nested `None`
    # has no accumulator level to delete from and survives as a literal null.
    layers = [{"a": 1}, {"a": {"b": None}}]

    result = merge_layers(layers)

    assert result == {"a": {"b": None}}


def test_merge_layers_nested_none_via_recursive_merge_deletes() -> None:
    # Both sides are Mappings here, so rule 2 recurses, and the nested
    # `None` deletes the key at that nested level (rule 1, inside the
    # recursive call).
    layers = [{"a": {"b": 1, "c": 2}}, {"a": {"b": None}}]

    result = merge_layers(layers)

    assert result == {"a": {"c": 2}}


def test_merge_layers_empty_returns_empty_dict() -> None:
    assert merge_layers([]) == {}


def test_merge_layers_mapping_scalar_replacement_both_directions() -> None:
    assert merge_layers([{"a": {"b": 1}}, {"a": 5}]) == {"a": 5}
    assert merge_layers([{"a": 5}, {"a": {"b": 1}}]) == {"a": {"b": 1}}


def test_merge_layers_three_deep_nesting() -> None:
    layers = [
        {"a": {"b": {"c": 1, "d": 1}}},
        {"a": {"b": {"c": 2}}},
    ]

    result = merge_layers(layers)

    assert result == {"a": {"b": {"c": 2, "d": 1}}}


def test_merge_layers_append_on_non_list_conflict_falls_back_to_replace() -> None:
    layers = [{"a": [1, 2]}, {"a": "not-a-list"}]

    result = merge_layers(layers, list_strategy="append")

    assert result == {"a": "not-a-list"}

    layers2 = [{"a": "not-a-list"}, {"a": [1, 2]}]
    result2 = merge_layers(layers2, list_strategy="append")

    assert result2 == {"a": [1, 2]}


# --- R6: never mutates inputs ------------------------------------------------


def test_merge_layers_does_not_mutate_inputs() -> None:
    layers = [
        {"a": {"x": 1, "y": 1}, "l": [1]},
        {"a": {"y": 2, "z": None}, "l": [2]},
    ]
    snapshot = copy.deepcopy(layers)

    result = merge_layers(layers)

    assert layers == snapshot

    result["a"]["x"] = 999
    result["l"].append(999)

    assert layers == snapshot


def test_merge_layers_does_not_mutate_inputs_with_append_strategy() -> None:
    layers = [
        {"a": {"x": 1, "y": 1}, "l": [1]},
        {"a": {"y": 2, "z": None}, "l": [2]},
    ]
    snapshot = copy.deepcopy(layers)

    result = merge_layers(layers, list_strategy="append")

    assert layers == snapshot

    result["a"]["x"] = 999
    result["l"].append(999)

    assert layers == snapshot


# --- Regression: aliased nested mappings must not leak mutation to siblings -


def test_merge_layers_aliased_nested_mapping_does_not_corrupt_sibling() -> None:
    """Regression for a real bug: the base-layer deepcopy preserves the
    *input's own* aliasing — if two keys point at the same nested mapping
    object (as YAML anchors/aliases produce), `deepcopy` gives them the same
    object in the copy too. Merging a later layer's change into one of those
    keys must not mutate that shared object in place, or the sibling key
    that happens to alias it gets corrupted along with it.
    """
    shared = {"x": 1}
    base = {"a": shared, "b": shared}
    assert base["a"] is base["b"]  # the aliasing this test relies on

    result = merge_layers([base, {"a": {"y": 2}}])

    assert result["a"] == {"x": 1, "y": 2}
    # `b` must be unaffected by the merge into `a`, even though both were
    # the same object in the deepcopy'd base.
    assert result["b"] == {"x": 1}
    assert result["a"] is not result["b"]

    # The original input's aliasing must also survive untouched (merge_layers
    # never mutates its inputs).
    assert base["a"] is base["b"]
    assert base["a"] == {"x": 1}


# --- R7: exported from the package root -------------------------------------


def test_merge_layers_is_exported() -> None:
    import lib_python_config

    assert lib_python_config.merge_layers is merge_layers
    assert "merge_layers" in lib_python_config.__all__
