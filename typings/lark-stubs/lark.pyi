"""Complete the Lark entry-point signatures used by this repository."""

from collections.abc import Callable, Collection, Iterator, Mapping
from typing import BinaryIO, Literal, TypeAlias

from lark.common import LexerConf
from lark.exceptions import UnexpectedInput
from lark.grammar import Rule
from lark.lexer import Token
from lark.parser_frontends import ParsingFrontend
from lark.parsers.lalr_interactive_parser import InteractiveParser
from lark.tree import Tree

from lark_cython import Token as NativeToken

_LexerCallback: TypeAlias = Callable[..., Token | NativeToken | None]

class LarkOptions:
    start: list[str]

class Lark:
    rules: list[Rule]
    options: LarkOptions
    lexer_conf: LexerConf
    parser: ParsingFrontend
    def __init__(
        self,
        grammar: str,
        *,
        parser: Literal["earley", "lalr", "cyk", "auto"] = "earley",
        lexer: Literal[
            "auto", "basic", "contextual", "dynamic", "dynamic_complete"
        ] = "auto",
        start: str | list[str] = "start",
        transformer: object = None,
        propagate_positions: bool | Callable[[object], bool] = False,
        maybe_placeholders: bool = True,
        lexer_callbacks: Mapping[str, _LexerCallback] | None = None,
        _plugins: Mapping[str, object] | None = None,
        **options: object,
    ) -> None: ...
    def parse(
        self,
        text: str | bytes,
        start: str | None = None,
        on_error: Callable[[UnexpectedInput], bool] | None = None,
    ) -> Tree[Token]: ...
    def parse_interactive(
        self, text: str | bytes | None = None, start: str | None = None
    ) -> InteractiveParser: ...
    def lex(self, text: str | bytes, dont_ignore: bool = False) -> Iterator[Token]: ...
    def save(self, f: BinaryIO, exclude_options: Collection[str] = ()) -> None: ...
    @classmethod
    def load(cls, f: BinaryIO) -> Lark: ...
