"""Python-facing types for the native extension's public API."""

from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from re import Pattern
from types import ModuleType
from typing import Protocol, TypedDict, overload

from lark.common import LexerConf, ParserConf
from lark.grammar import Rule
from lark.lexer import TerminalDef
from lark.lexer import Token as PythonToken

class Token:
    type: str
    value: str
    start_pos: int
    line: int
    column: int
    end_line: int | None
    end_column: int | None
    end_pos: int | None
    def __init__(
        self,
        type_: str,
        value: str,
        start_pos: int = -1,
        line: int = -1,
        column: int = -1,
        end_line: int | None = None,
        end_column: int | None = None,
        end_pos: int | None = None,
    ) -> None: ...
    def update(self, type_: str | None = None, value: str | None = None) -> Token: ...
    @classmethod
    def new_borrow_pos(cls, type_: str, value: str, borrow_t: Token) -> Token: ...
    def __deepcopy__(self, memo: dict[int, object]) -> Token: ...
    def __eq__(self, other: object) -> bool: ...
    def __hash__(self) -> int: ...
    def __lark_meta__(self) -> Token: ...

# Lark and generated standalone modules supply distinct configuration classes.
class Lexer:
    def make_lexer_state(self, text: str) -> LexerState: ...
    def make_lexer_thread(self, text: str) -> LexerThread: ...

class BasicLexer(Lexer):
    def __init__(self, conf: LexerConf) -> None: ...
    def lex(
        self, state: LexerState, parser_state: ParserState | None
    ) -> Iterator[Token]: ...
    def next_token(
        self, lex_state: LexerState, parser_state: ParserState | None
    ) -> Token: ...

class ContextualLexer(Lexer):
    def __init__(
        self,
        conf: LexerConf,
        states: Mapping[int, Collection[str]],
        always_accept: Collection[str] = (),
    ) -> None: ...
    def lex(
        self, lexer_state: LexerState, parser_state: ParserState
    ) -> Iterator[Token]: ...
    def next_token(
        self, lexer_state: LexerState, parser_state: ParserState
    ) -> Token: ...

class LineCounter:
    newline_char: str
    char_pos: int
    line: int
    column: int
    line_start_pos: int
    def __init__(self, newline_char: str) -> None: ...
    def feed(self, token: str, test_newline: bool = True) -> None: ...

class LexerState:
    text: str
    line_ctr: LineCounter
    last_token: Token | None
    def __init__(
        self, text: str, line_ctr: LineCounter, last_token: Token | None = None
    ) -> None: ...

class LexerThread:
    state: LexerState
    lexer: Lexer
    def __init__(self, lexer: Lexer, lexer_state: LexerState) -> None: ...
    @classmethod
    def from_text(cls, lexer: Lexer, text: str) -> LexerThread: ...
    def lex(self, parser_state: ParserState | None) -> Iterator[Token]: ...
    def next_token(self, parser_state: ParserState) -> Token: ...

class Scanner:
    def __init__(
        self,
        terminals: Sequence[TerminalDef],
        g_regex_flags: int,
        re_: ModuleType,
        use_bytes: bool,
        match_whole: bool = False,
    ) -> None: ...
    def _build_mres(
        self, terminals: Sequence[TerminalDef], max_size: int
    ) -> list[tuple[Pattern[str] | Pattern[bytes], dict[int, str]]]: ...
    @overload
    def match(self, text: str, pos: int) -> tuple[str, str] | None: ...
    @overload
    def match(self, text: bytes, pos: int) -> tuple[bytes, str] | None: ...

class ParserState:
    lexer: LexerThread
    state_stack: list[int]
    value_stack: list[object]
    def copy(self, deepcopy_values: bool = True) -> ParserState: ...
    def feed_token(
        self, token: Token | PythonToken, is_end: bool = False
    ) -> object: ...

class InteractiveParser:
    parser_state: ParserState
    lexer_thread: LexerThread
    def copy(self, deepcopy_values: bool = True) -> InteractiveParser: ...
    def accepts(self) -> set[str]: ...
    def iter_parse(self) -> Iterator[Token]: ...
    def exhaust_lexer(self) -> list[Token]: ...
    def feed_token(self, token: Token | PythonToken) -> object: ...
    def feed_eof(self, last_token: Token | PythonToken | None = None) -> object: ...
    def resume_parse(self) -> object: ...

class LALR_Parser:  # noqa: N801 - Match the extension's class name.
    def __init__(
        self, parser_conf: ParserConf, debug: bool = False, strict: bool = False
    ) -> None: ...
    def parse(
        self,
        lexer: LexerThread,
        start: str,
        on_error: Callable[..., bool] | None = None,
    ) -> object: ...

class Meta:
    empty: bool
    line: int
    column: int
    start_pos: int
    end_line: int
    end_column: int
    end_pos: int
    container_line: int
    container_column: int
    container_start_pos: int
    container_end_line: int
    container_end_column: int
    container_end_pos: int

class Tree:
    data: object
    children: list[object]
    def __init__(
        self, data: object, children: list[object], meta: Meta | None = None
    ) -> None: ...
    @property
    def meta(self) -> Meta: ...
    def __lark_meta__(self) -> Meta: ...
    def pretty(self, indent_str: str = "  ") -> str: ...
    def iter_subtrees(self) -> Iterator[Tree]: ...
    def iter_subtrees_topdown(self) -> Iterator[Tree]: ...
    def find_pred(self, pred: Callable[[Tree], bool]) -> Iterator[Tree]: ...
    def find_data(self, data: str) -> Iterator[Tree]: ...
    def expand_kids_by_data(self, *data_values: str) -> bool: ...
    def scan_values(self, pred: Callable[[object], bool]) -> Iterator[object]: ...
    def copy(self) -> Tree: ...
    def set(self, data: str, children: list[object]) -> None: ...

class ParseTreeBuilder:
    def __init__(
        self,
        rules: list[Rule],
        tree_class: Callable[..., object],
        propagate_positions: bool | Callable[[object], bool] = False,
        ambiguous: bool = False,
        maybe_placeholders: bool = False,
    ) -> None: ...
    def create_callback(
        self, transformer: object = None
    ) -> dict[Rule, Callable[[list[object]], object]]: ...

class ChildFilter:
    def __init__(
        self,
        to_include: list[tuple[int, bool, int]],
        append_none: int,
        node_builder: Callable[[list[object]], object],
    ) -> None: ...
    def __call__(self, children: list[object]) -> object: ...

class ChildFilterLALR(ChildFilter): ...

# The private Lark plugin hooks have heterogeneous call signatures and results.
plugins: Plugins

class BasicLexerFactory(Protocol):
    """Construct a native basic lexer."""

    def __call__(self, conf: LexerConf) -> BasicLexer: ...

class ContextualLexerFactory(Protocol):
    """Construct a native contextual lexer."""

    def __call__(
        self,
        conf: LexerConf,
        states: Mapping[int, Collection[str]],
        always_accept: Collection[str] = (),
    ) -> ContextualLexer: ...

class Plugins(TypedDict):
    """The five hooks replaced by the native implementation."""

    BasicLexer: BasicLexerFactory
    ContextualLexer: ContextualLexerFactory
    LexerThread: Callable[..., object]
    LALR_Parser: Callable[..., object]
    _Parser: Callable[..., object]
