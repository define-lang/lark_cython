"""Bind native plugins to the classes in a generated Lark parser."""

from __future__ import annotations

from copy import copy
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from lark.common import LexerConf

    from .lark_cython import Plugins

from .lark_cython import BasicLexer, ContextualLexer, plugins


def standalone_plugins(module: Any) -> Plugins:
    """Return plugins for a module produced by Lark's standalone generator."""
    # Generated modules define their own classes, including the base below.

    class InteractiveParser(module.InteractiveParser):
        def copy(self, deepcopy_values: bool = True) -> InteractiveParser:  # noqa: FBT001, FBT002 - Match Lark's API.
            state = self.parser_state.copy(deepcopy_values=deepcopy_values)
            lexer = copy(self.lexer_thread)
            state.lexer = lexer
            return type(self)(self.parser, state, lexer)

    runtime = SimpleNamespace(
        Token=module.Token,
        TerminalDef=module.TerminalDef,
        create_unless=module._create_unless,
        LexError=module.LexError,
        UnexpectedInput=module.UnexpectedInput,
        UnexpectedToken=module.UnexpectedToken,
        UnexpectedCharacters=module.UnexpectedCharacters,
        InteractiveParser=InteractiveParser,
    )

    def configure(conf: LexerConf) -> LexerConf:
        configured = copy(conf)
        # This adapter adds an attribute absent from the input configuration.
        setattr(configured, "_lark_cython_runtime", runtime)  # noqa: B010
        return configured

    def basic_lexer(conf: LexerConf) -> BasicLexer:
        return BasicLexer(configure(conf))

    def contextual_lexer(
        conf: LexerConf,
        states: Mapping[int, Collection[str]],
        always_accept: Collection[str] = (),
    ) -> ContextualLexer:
        return ContextualLexer(configure(conf), states, always_accept=always_accept)

    return {**plugins, "BasicLexer": basic_lexer, "ContextualLexer": contextual_lexer}
