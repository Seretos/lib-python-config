"""Deterministic deep-merge of layered config mappings.

`merge_layers` folds a sequence of config layers — typically the `existing`
list returned by `resolve_config_paths`, ordered lowest-priority-first (e.g.
home → outer repo → inner repo) — into a single mapping, with later layers
taking priority. It carries no schema knowledge and performs no validation;
it only knows how to combine mappings, lists, and scalars.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any, Literal


def _merge_into(
    acc: dict[str, Any],
    layer: Mapping[str, Any],
    *,
    list_strategy: Literal["replace", "append"],
) -> None:
    """Fold `layer` into `acc` in place, key by key, applying this order:

      1. `layer[key] is None` → delete `key` from `acc` unconditionally
         (`pop(key, None)`, a no-op if absent), regardless of what `acc`
         currently holds there — scalar, list, mapping, or nothing. This
         check runs *before* any type check below.
      2. else both `acc.get(key)` and `layer[key]` are `Mapping` → recurse
         this same rule set into that nested level.
      3. else both are `list` and `list_strategy == "append"` → concatenate
         (later layer's elements appended after the accumulator's).
      4. else the later value wins outright — `acc[key]` is replaced
         wholesale with a deep copy of `layer[key]`.

    Every value ever written into `acc` is a deep copy of something taken
    from `layer` (or, for lists under `append`, a deep copy of both sides
    combined into a new list) — `acc` never ends up aliasing a container
    from any input layer.
    """
    for key, value in layer.items():
        if value is None:
            acc.pop(key, None)
            continue

        current = acc.get(key)

        if isinstance(current, Mapping) and isinstance(value, Mapping):
            # Always start from a fresh, independent dict before recursing —
            # never mutate whatever object `acc.get(key)` happens to be.
            # `acc` is deep-copied from the base layer, and `deepcopy`
            # faithfully preserves the *input's own* aliasing (e.g. two keys
            # that pointed at the same nested mapping via a YAML anchor end
            # up pointing at the same object in `acc` too). Mutating that
            # object in place would corrupt every other key aliased to it;
            # copying first breaks the alias before any mutation happens.
            current = dict(current)
            _merge_into(current, value, list_strategy=list_strategy)
            acc[key] = current
            continue

        if (
            list_strategy == "append"
            and isinstance(current, list)
            and isinstance(value, list)
        ):
            acc[key] = current + deepcopy(value)
            continue

        acc[key] = deepcopy(value)


def merge_layers(
    layers: Sequence[Mapping[str, Any]],
    *,
    list_strategy: Literal["replace", "append"] = "replace",
) -> dict[str, Any]:
    """Deep-merge layered config mappings, later layers taking priority.

    `layers` is ordered lowest-priority-first — the same order
    `resolve_config_paths` returns its `existing` list in. The first layer
    is the **base**: it is deep-copied verbatim, never merged, so a literal
    `None` value in the first layer is preserved as-is (`merge_layers([x])
    == x`, value-equal but never aliased to `x`). Every later layer is then
    folded into the accumulator key by key via the rule set documented on
    `_merge_into`.

    Consequences worth calling out (all intended):

      - A later layer's `None` at a key **deletes** that key, no matter what
        the accumulator held there before (scalar, list, mapping, absent).
      - A later layer's mapping that **wholesale-replaces** a non-mapping
        value (rule 4, not the recursive rule 2) carries its own nested
        `None`s through as **literal nulls**, not deletions — there is no
        accumulator level under the replaced value to delete from. Only a
        `None` reached by recursing into two already-matching mappings
        (rule 2) deletes.
      - `list_strategy="append"` only concatenates when *both* sides are
        lists; a list meeting a non-list (either direction) falls back to
        wholesale replacement (rule 4) rather than raising, since this
        function has no schema to validate against.
      - No input mapping, list, or nested container is ever mutated, and the
        result never aliases a container from any input layer.

    An empty `layers` sequence returns `{}`.
    """
    if not layers:
        return {}

    result: dict[str, Any] = deepcopy(dict(layers[0]))
    for layer in layers[1:]:
        _merge_into(result, layer, list_strategy=list_strategy)
    return result
