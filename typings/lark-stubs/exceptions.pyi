"""Types for diagnostic fields assigned by Lark's exception constructors."""

from lark.parsers.lalr_interactive_parser import InteractiveParser

class LarkError(Exception): ...
class ConfigurationError(LarkError, ValueError): ...
class GrammarError(LarkError): ...
class ParseError(LarkError): ...
class LexError(LarkError): ...

class UnexpectedInput(LarkError):
    line: int
    column: int
    pos_in_stream: int | None
    interactive_parser: InteractiveParser
    def get_context(self, text: str, span: int = 40) -> str: ...

class UnexpectedCharacters(LexError, UnexpectedInput):
    allowed: set[str]
    token_history: list[object] | None

class UnexpectedToken(ParseError, UnexpectedInput):
    token: object
    expected: set[str]
    @property
    def accepts(self) -> set[str]: ...

class UnexpectedEOF(ParseError, UnexpectedInput): ...
