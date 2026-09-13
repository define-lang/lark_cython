"""Preserve decorated types and allow transformer reductions to return scalars."""

from collections.abc import Callable
from typing import Generic, TypeVar

from lark.tree import Branch, Meta, Tree

_Leaf = TypeVar("_Leaf")
_Result = TypeVar("_Result")
_Decorated = TypeVar("_Decorated")

class Transformer(Generic[_Leaf, _Result]):
    def __init__(self, visit_tokens: bool = True) -> None: ...
    def transform(self, tree: Tree[_Leaf]) -> _Result: ...
    def __default__(
        self, data: str, children: list[Branch[_Leaf]], meta: Meta | None
    ) -> object: ...

class Transformer_InPlace(Transformer[_Leaf, _Result]): ...  # noqa: N801 - Lark API.
class Transformer_NonRecursive(Transformer[_Leaf, _Result]): ...  # noqa: N801 - Lark API.

def v_args(
    inline: bool = False,
    meta: bool = False,
    tree: bool = False,
    wrapper: Callable[..., object] | None = None,
) -> Callable[[_Decorated], _Decorated]: ...
