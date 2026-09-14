"""Use native lexers and parsing with a generated Lark module."""

from copy import copy
from types import SimpleNamespace

from .lark_cython import BasicLexer, ContextualLexer, plugins


def standalone_plugins(module):
    """Bind the plugins to a generated module's tokens and exception classes."""
    class InteractiveParser(module.InteractiveParser):
        def copy(self, deepcopy_values=True):
            state = self.parser_state.copy(deepcopy_values=deepcopy_values)
            lexer = copy(self.lexer_thread)
            state.lexer = lexer
            return type(self)(self.parser, state, lexer)

    runtime = SimpleNamespace(
        Token=module.Token, TerminalDef=module.TerminalDef,
        create_unless=module._create_unless,
        LexError=module.LexError, UnexpectedInput=module.UnexpectedInput,
        UnexpectedToken=module.UnexpectedToken,
        UnexpectedCharacters=module.UnexpectedCharacters,
        InteractiveParser=InteractiveParser,
    )

    def configure(conf):
        configured = copy(conf)
        configured._lark_cython_runtime = runtime
        return configured

    def basic_lexer(conf):
        return BasicLexer(configure(conf))

    def contextual_lexer(conf, states, always_accept=()):
        return ContextualLexer(configure(conf), states, always_accept)

    return dict(plugins, BasicLexer=basic_lexer, ContextualLexer=contextual_lexer)
