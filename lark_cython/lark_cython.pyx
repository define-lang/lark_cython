# cython: language_level=3, freethreading_compatible=True
from lark.visitors import _vargs_meta, _vargs_meta_inline
from lark.visitors import Transformer_InPlace
from functools import partial, wraps
from lark.parsers.lalr_interactive_parser import (
    InteractiveParser as LarkInteractiveParser,
)
from lark.parsers.lalr_analysis import LALR_Analyzer, Shift, IntParseTable
from lark.utils import Serialize
import cython
from threading import RLock
from types import SimpleNamespace

from copy import copy, deepcopy
from typing import Any, Iterator, Optional, Collection, Dict

from lark.exceptions import (
    ConfigurationError, GrammarError, LexError, UnexpectedCharacters,
    UnexpectedInput, UnexpectedToken,
)
from lark.lexer import CallChain, _create_unless, TerminalDef, _regexp_has_newline
from lark.lexer import Token as LarkToken


@cython.freelist(10240)
cdef class Token:
    cdef public str type
    cdef public int start_pos
    cdef public str value
    cdef public int line
    cdef public int column
    cdef public end_line
    cdef public end_column
    cdef public end_pos

    def __cinit__(
        self, str type_, str value, int start_pos=-1, int line=-1,
        int column=-1, end_line=None, end_column=None, end_pos=None,
    ):
        self.type = type_
        self.start_pos = start_pos
        self.value = value
        self.line = line
        self.column = column
        self.end_line = end_line
        self.end_column = end_column
        self.end_pos = end_pos

    cpdef update(self, type_: Optional[str]=None, value: Optional[Any]=None):
        return Token.new_borrow_pos(
            type_ if type_ is not None else self.type,
            value if value is not None else self.value,
            self
        )

    @classmethod
    def new_borrow_pos(cls, type_: str, value: Any, borrow_t: Token):
        return cls(
            type_, value, borrow_t.start_pos, borrow_t.line, borrow_t.column,
            borrow_t.end_line, borrow_t.end_column, borrow_t.end_pos,
        )

    def __reduce__(self):
        return (
            self.__class__,
            (self.type, self.value, self.start_pos, self.line, self.column,
             self.end_line, self.end_column, self.end_pos),
        )

    def __repr__(self):
        return "Token(%r, %r)" % (self.type, self.value)

    def __str__(self):
        return self.value

    def __deepcopy__(self, memo):
        return type(self).new_borrow_pos(self.type, self.value, self)

    def __eq__(self, other):
        if isinstance(other, Token):
            return self.type == other.type and self.value == other.value

        if isinstance(other, str):
            return self.value == other

        return NotImplemented

    def __hash__(self):
        return hash(self.value)

    def __lark_meta__(self):
        return self

cdef Token _to_native_token(token):
    return Token(
        token.type, token.value,
        token.start_pos if token.start_pos is not None else -1,
        token.line if token.line is not None else -1,
        token.column if token.column is not None else -1,
        token.end_line, token.end_column, token.end_pos,
    )


cdef class LexerState:
    __slots__ = "text", "line_ctr", "last_token", "_scanner_cache"

    cdef public str text
    cdef public LineCounter line_ctr
    cdef public object last_token
    cdef dict _scanner_cache

    def __init__(self, text, line_ctr, last_token=None):
        self.text = text
        self.line_ctr = line_ctr
        self.last_token = last_token
        self._scanner_cache = {}

    def __eq__(self, other):
        if not isinstance(other, LexerState):
            return NotImplemented

        return (
            self.text is other.text
            and self.line_ctr == other.line_ctr
            and self.last_token == other.last_token
        )

    def __copy__(self):
        cdef LexerState result = type(self)(
            self.text, copy(self.line_ctr), self.last_token)
        result._scanner_cache.update(self._scanner_cache)
        return result

    _Token = Token

cdef class LineCounter:
    __slots__ = "char_pos", "line", "column", "line_start_pos", "newline_char"

    cdef public str newline_char
    cdef public int char_pos
    cdef public int line
    cdef public int column
    cdef public int line_start_pos

    def __cinit__(self, newline_char):
        self.newline_char = newline_char
        self.char_pos = 0
        self.line = 1
        self.column = 1
        self.line_start_pos = 0

    def __eq__(self, other):
        if not isinstance(other, LineCounter):
            return NotImplemented

        return (
            self.char_pos == other.char_pos
            and self.newline_char == other.newline_char
        )

    def __copy__(self):
        result = type(self)(self.newline_char)
        result.char_pos = self.char_pos
        result.line = self.line
        result.column = self.column
        result.line_start_pos = self.line_start_pos
        return result

    cpdef feed(self, str token, bint test_newline=True):
        """Consume a token and calculate the new line & column.

        Set test_newline=False if token does not contain a newline.
        """
        cdef int newlines

        if test_newline:
            newlines = token.count(self.newline_char)
            if newlines:
                self.line += newlines
                self.line_start_pos = self.char_pos + \
                    token.rindex(self.newline_char) + 1

        self.char_pos += len(token)
        self.column = self.char_pos - self.line_start_pos + 1


cdef class Scanner:
    cdef public terminals
    cdef public int g_regex_flags
    cdef public re_
    cdef public use_bytes
    cdef public match_whole
    cdef public allowed_types
    cdef list _mres

    def __cinit__(self, terminals, g_regex_flags, re_, use_bytes, match_whole=False):
        self.terminals = terminals
        self.g_regex_flags = g_regex_flags
        self.re_ = re_
        self.use_bytes = use_bytes
        self.match_whole = match_whole

        self.allowed_types = {t.name for t in self.terminals}

        self._mres = self._build_mres(terminals, len(terminals))

    def _build_mres(self, terminals, max_size):
        postfix = "$" if self.match_whole else ""
        mres = []
        while terminals:
            pattern = u"|".join(u"(?P<%s>%s)" % (
                t.name, t.pattern.to_regexp() + postfix) for t in terminals[:max_size])
            if self.use_bytes:
                pattern = pattern.encode("latin-1")
            mre = self.re_.compile(pattern, self.g_regex_flags)

            mres.append((mre, {i: n for n, i in mre.groupindex.items()}))
            terminals = terminals[max_size:]
        return mres

    cpdef public match(self, text, pos: int):
        for mre, type_from_index in self._mres:
            m = mre.match(text, pos)
            if m:
                return m.group(0), type_from_index[m.lastindex]


cdef class Lexer:
    """Lexer interface

    Method Signatures:
        lex(self, lexer_state, parser_state) -> Iterator[Token]
    """
    cdef public object _runtime

    # def lex(self, lexer_state: LexerState, parser_state: Any) -> Iterator[Token]:
    #    return NotImplemented

    cpdef make_lexer_state(self, str text):
        line_ctr = LineCounter(b"\n" if isinstance(text, bytes) else "\n")
        return LexerState(text, line_ctr)

    cpdef make_lexer_thread(self, str text):
        return LexerThread.from_text(self, text)

cdef class BasicLexer(Lexer):

    cdef list terminals  # : Collection[TerminalDef]
    cdef frozenset ignore_types  # : FrozenSet[str]
    cdef frozenset newline_types  # : FrozenSet[str]
    cdef dict user_callbacks  # : Dict[str, _Callback]
    cdef dict callback  # : Dict[str, _Callback]
    cdef object re

    cdef int g_regex_flags
    cdef int use_bytes
    cdef dict terminals_by_name
    cdef Scanner _scanner
    cdef object _scanner_lock
    cdef object _scanner_cache_key

    def __init__(self, conf: "LexerConf") -> None:
        self._runtime = getattr(conf, "_lark_cython_runtime", _DEFAULT_RUNTIME)
        terminals = list(conf.terminals)
        assert all(
            isinstance(t, self._runtime.TerminalDef) for t in terminals), terminals

        self.re = conf.re_module
        self.ignore_types = frozenset(conf.ignore)

        if not conf.skip_validation:
            terminal_names = {t.name for t in terminals}
            # Sanitization
            for t in terminals:
                try:
                    self.re.compile(t.pattern.to_regexp(), conf.g_regex_flags)
                except self.re.error:
                    raise self._runtime.LexError(
                        "Cannot compile token %s: %s" % (t.name, t.pattern))

                if t.pattern.min_width == 0:
                    raise self._runtime.LexError(
                        "Lexer does not allow zero-width terminals. (%s: %s)"
                        % (t.name, t.pattern)
                    )

            undefined_ignore_types = self.ignore_types - terminal_names
            if undefined_ignore_types:
                raise self._runtime.LexError(
                    "Ignore terminals are not defined: %s"
                    % undefined_ignore_types)

        # Init
        self.newline_types = frozenset(
            t.name for t in terminals if _regexp_has_newline(t.pattern.to_regexp()))

        terminals.sort(key=lambda x: (-x.priority, -
                       x.pattern.max_width, -len(x.pattern.value), x.name))
        self.terminals = terminals
        self.user_callbacks = conf.callbacks
        self.g_regex_flags = conf.g_regex_flags
        self.use_bytes = conf.use_bytes
        self.terminals_by_name = conf.terminals_by_name

        self._scanner_lock = RLock()
        self._scanner_cache_key = object()
        self._scanner = None

    cdef _build_scanner(self):
        terminals, self.callback = self._runtime.create_unless(
            self.terminals, self.g_regex_flags, self.re, self.use_bytes)
        assert all(self.callback.values())

        for type_, f in self.user_callbacks.items():
            if type_ in self.callback:
                # Already a callback there, probably UnlessCallback
                self.callback[type_] = CallChain(
                    self.callback[type_], f,
                    lambda t, expected=type_: t.type == expected)
            else:
                self.callback[type_] = f

        self._scanner = Scanner(terminals, self.g_regex_flags, self.re, self.use_bytes)

    @property
    def scanner(self):
        # Publish the scanner and its complete callback table together.
        # Wait for initialization to finish before using the scanner.
        with self._scanner_lock:
            if self._scanner is None:
                self._build_scanner()
            return self._scanner

    cdef Scanner _scanner_for_state(self, LexerState state):
        # Avoid taking the shared initialization lock for every token.
        cdef Scanner scanner = state._scanner_cache.get(self._scanner_cache_key)
        if scanner is None:
            scanner = self.scanner
            state._scanner_cache[self._scanner_cache_key] = scanner
        return scanner

    def lex(self, state, parser_state):
        try:
            while True:
                yield self.next_token(state, parser_state)
        except EOFError:
            return

    cpdef public next_token(self, LexerState lex_state, ParserState parser_state):
        cdef LineCounter line_ctr = lex_state.line_ctr
        cdef str value
        cdef str type_
        cdef Token t
        cdef Token t2
        cdef Scanner scanner

        if line_ctr.char_pos >= len(lex_state.text):
            raise EOFError(self)

        scanner = self._scanner_for_state(lex_state)

        while line_ctr.char_pos < len(lex_state.text):
            res = scanner.match(lex_state.text, line_ctr.char_pos)
            if not res:
                allowed = scanner.allowed_types - self.ignore_types
                if not allowed:
                    allowed = {"<END-OF-FILE>"}
                raise self._runtime.UnexpectedCharacters(
                    lex_state.text, line_ctr.char_pos,
                    line_ctr.line, line_ctr.column,
                    allowed=allowed,
                    token_history=lex_state.last_token and [lex_state.last_token],
                    state=parser_state,
                    terminals_by_name=self.terminals_by_name,
                )

            value, type_ = res

            if type_ not in self.ignore_types:
                t = Token(type_, value, line_ctr.char_pos,
                          line_ctr.line, line_ctr.column)
                line_ctr.feed(value, type_ in self.newline_types)
                t.end_line = line_ctr.line
                t.end_column = line_ctr.column
                t.end_pos = line_ctr.char_pos
                if t.type in self.callback:
                    callback_result = self.callback[t.type](t)
                    if isinstance(callback_result, self._runtime.Token):
                        callback_result = _to_native_token(callback_result)
                    if not isinstance(callback_result, Token):
                        raise self._runtime.LexError(
                            "Callbacks must return a token (returned %r)"
                            % callback_result)
                    t = callback_result
                lex_state.last_token = t
                return t
            else:
                if type_ in self.callback:
                    t2 = Token(type_, value, line_ctr.char_pos,
                               line_ctr.line, line_ctr.column)
                    self.callback[type_](t2)
                line_ctr.feed(value, type_ in self.newline_types)

        # EOF
        raise EOFError(self)

cdef class ContextualLexer(Lexer):

    cdef dict lexers  # : Dict[str, BasicLexer]
    cdef BasicLexer root_lexer

    def __cinit__(
        self, conf: "LexerConf", states: Dict[str, Collection[str]],
        always_accept: Collection[str] = (),
    ):

        self._runtime = getattr(conf, "_lark_cython_runtime", _DEFAULT_RUNTIME)
        terminals = list(conf.terminals)
        terminals_by_name = conf.terminals_by_name

        trad_conf = copy(conf)
        trad_conf.terminals = terminals

        lexer_by_tokens: Dict[FrozenSet[str], BasicLexer] = {}
        extra_accepts = set(conf.ignore).union(always_accept)
        self.lexers = {}
        for state, accepts in states.items():
            key = frozenset(accepts)
            try:
                lexer = lexer_by_tokens[key]
            except KeyError:
                accepts = set(accepts) | extra_accepts
                lexer_conf = copy(trad_conf)
                lexer_conf.terminals = [terminals_by_name[n]
                                        for n in accepts if n in terminals_by_name]
                lexer = BasicLexer(lexer_conf)
                lexer_by_tokens[key] = lexer

            self.lexers[state] = lexer

        self.root_lexer = BasicLexer(trad_conf)

    cpdef public make_lexer_state(self, str text):
        return self.root_lexer.make_lexer_state(text)

    cpdef public next_token(self, LexerState lexer_state, ParserState parser_state):
        cdef BasicLexer lexer
        cdef Token last_token
        cdef Token token
        try:
            lexer = self.lexers[parser_state.position]
            return lexer.next_token(lexer_state, parser_state)
        except self._runtime.UnexpectedCharacters as e:
            # The terminal may be defined, but not in the current context.
            # This tests the input against the global context, to provide a nicer error.
            try:
                # Preserve last_token before root_lexer.next_token changes it.
                last_token = lexer_state.last_token
                token = self.root_lexer.next_token(lexer_state, parser_state)
                raise self._runtime.UnexpectedToken(
                    token, e.allowed, state=parser_state,
                    token_history=[last_token],
                    terminals_by_name=self.root_lexer.terminals_by_name,
                )
            except self._runtime.UnexpectedCharacters:
                # The root lexer has the wrong expected set; use the original.
                raise e

    def lex(self, lexer_state: LexerState, parser_state: Any) -> Iterator[Token]:
        try:
            while True:
                yield self.next_token(lexer_state, parser_state)
        except EOFError:
            pass


cdef class LexerThread:
    """Tie a lexer instance and its state together for the parser."""

    cdef Lexer lexer
    cdef public object _runtime
    cdef public LexerState state

    def __init__(self, lexer, LexerState lexer_state):
        self.lexer = lexer
        self._runtime = lexer._runtime
        self.state = lexer_state

    @classmethod
    def from_text(cls, lexer, text):
        return cls(lexer, lexer.make_lexer_state(text))

    def next_token(self, ParserState parser_state):
        return self.lexer.next_token(self.state, parser_state)

    def __copy__(self):
        return type(self)(self.lexer, copy(self.state))

    def lex(self, parser_state):
        return self.lexer.lex(self.state, parser_state)

    _Token = Token

####


cdef class ParseConf:
    __slots__ = (
        "parse_table", "callbacks", "start_state", "end_state", "states",
    )

    cdef public parse_table
    cdef public object _runtime
    cdef public int start_state, end_state
    cdef dict states
    cdef public dict callbacks

    def __init__(self, parse_table, callbacks, start, runtime=None):
        self._runtime = _DEFAULT_RUNTIME if runtime is None else runtime
        self.parse_table = parse_table
        self.start_state = parse_table.start_states[start]
        self.end_state = parse_table.end_states[start]
        self.states = parse_table.states

        self.callbacks = callbacks


cdef class ParserState:
    __slots__ = "parse_conf", "lexer", "state_stack", "value_stack"

    cdef public ParseConf parse_conf
    cdef public object lexer   # LexerThread
    cdef public list value_stack, state_stack

    def __init__(self, parse_conf, lexer, state_stack=None, value_stack=None):
        self.parse_conf = parse_conf
        self.lexer = lexer
        self.state_stack = state_stack or [self.parse_conf.start_state]
        self.value_stack = value_stack or []

    @property
    def position(self):
        return self.state_stack[-1]

    # Necessary for match_examples() to work
    def __eq__(self, other):
        if not isinstance(other, ParserState):
            return NotImplemented
        return (
            len(self.state_stack) == len(other.state_stack)
            and self.position == other.position
        )

    def __copy__(self):
        return self.copy()

    def copy(self, deepcopy_values=True):
        return type(self)(
            self.parse_conf,
            self.lexer,
            copy(self.state_stack),
            deepcopy(self.value_stack) if deepcopy_values else copy(self.value_stack),
        )

    cpdef feed_token(self, token, bint is_end=False):
        if isinstance(token, (LarkToken, self.parse_conf._runtime.Token)):
            token = _to_native_token(token)
        elif not isinstance(token, Token):
            raise TypeError("feed_token expects a Lark or lark-cython Token")
        return self._feed_token(token, is_end)

    cdef _feed_token(self, Token token, bint is_end):
        cdef:
            list state_stack = self.state_stack
            list value_stack = self.value_stack
            dict states = self.parse_conf.states
            int end_state = self.parse_conf.end_state
            dict callbacks = self.parse_conf.callbacks

            int state, new_state
            object action, _action
            object arg
            int size
            list s
            object value
            object rule

        while True:
            state = state_stack[-1]
            try:
                action, arg = states[state][token.type]
            except KeyError:
                # expected = {s for s in states[state].keys() if s.isupper()}
                expected = set(filter(str.isupper, states[state].keys()))
                raise self.parse_conf._runtime.UnexpectedToken(
                    token, expected, state=self, interactive_parser=None)

            if action is Shift:
                # shift once and return
                assert not is_end
                assert arg != end_state
                state_stack.append(arg)
                value_stack.append(
                    token if token.type not in callbacks
                    else callbacks[token.type](token)
                )
                return
            else:
                # reduce+shift as many times as necessary
                rule = arg
                size = len(rule.expansion)
                if size:
                    s = value_stack[-size:]
                    del state_stack[-size:]
                    del value_stack[-size:]
                else:
                    s = []

                value = callbacks[rule](s) if callbacks else s

                _action, new_state = states[state_stack[-1]][rule.origin.name]
                assert _action is Shift
                state_stack.append(new_state)
                value_stack.append(value)

                if is_end and state_stack[-1] == end_state:
                    return value_stack[-1]


class InteractiveParser(LarkInteractiveParser):
    def copy(self, deepcopy_values=True):
        state = self.parser_state.copy(deepcopy_values=deepcopy_values)
        lexer = copy(self.lexer_thread)
        state.lexer = lexer
        return type(self)(self.parser, state, lexer)


cdef class _Parser:
    cdef parse_table
    cdef dict callbacks
    cdef bint debug

    def __cinit__(self, parse_table, callbacks, debug=False):
        self.parse_table = parse_table
        self.callbacks = callbacks
        self.debug = debug

    def parse(
        self, lexer, start, value_stack=None, state_stack=None,
        start_interactive=False,
    ):
        runtime = lexer._runtime
        parse_conf = ParseConf(self.parse_table, self.callbacks, start, runtime)
        parser_state = ParserState(parse_conf, lexer, state_stack, value_stack)
        if start_interactive:
            return runtime.InteractiveParser(self, parser_state, parser_state.lexer)
        return self.parse_from_state(parser_state)

    cpdef parse_from_state(self, ParserState state, Token last_token=None):
        # Main LALR-parser loop
        cdef Token token
        cdef Token end_token
        runtime = state.parse_conf._runtime

        try:
            token = last_token
            # for token in state.lexer.lex(state):
            try:
                while True:
                    token = state.lexer.next_token(state)
                    state._feed_token(token, False)
            except EOFError:
                pass

            end_token = Token.new_borrow_pos(
                "$END", "", token) if token else Token("$END", "", 0, 1, 1)
            return state._feed_token(end_token, True)
        except runtime.UnexpectedInput as e:
            e.interactive_parser = runtime.InteractiveParser(self, state, state.lexer)
            raise e
        except Exception:
            if self.debug:
                print("")
                print("STATE STACK DUMP")
                print("----------------")
                for i, s in enumerate(state.state_stack):
                    print("%d)" % i, s)
                print("")

            raise


class LALR_Parser(Serialize):
    def __init__(self, parser_conf, debug=False, strict=False):
        analysis = LALR_Analyzer(parser_conf, debug=debug, strict=strict)
        analysis.compute_lalr()
        callbacks = parser_conf.callbacks

        self._parse_table = (IntParseTable.from_ParseTable(analysis.parse_table)
                             if debug else analysis.parse_table)
        self.parser_conf = parser_conf
        self.parser = _Parser(self._parse_table, callbacks, debug)

    @classmethod
    def deserialize(cls, data, memo, callbacks, debug=False):
        inst = cls.__new__(cls)
        inst._parse_table = IntParseTable.deserialize(data, memo)
        inst.parser = _Parser(inst._parse_table, callbacks, debug)
        return inst

    def serialize(self, memo):
        return self._parse_table.serialize(memo)

    def parse_interactive(self, lexer, start):
        return self.parser.parse(lexer, start, start_interactive=True)

    def parse(self, lexer, start, on_error=None):
        runtime = lexer._runtime
        try:
            return self.parser.parse(lexer, start)
        except runtime.UnexpectedInput as e:
            if on_error is None:
                raise

            error = e

        return self._recover(error, on_error, runtime)

    def _recover(self, e, on_error, runtime):
        while True:
            if isinstance(e, runtime.UnexpectedCharacters):
                s = e.interactive_parser.lexer_thread.state
                p = s.line_ctr.char_pos

            if not on_error(e):
                raise e

            if isinstance(e, runtime.UnexpectedCharacters):
                # If user didn't change the character position, then we should
                if p == s.line_ctr.char_pos:
                    s.line_ctr.feed(s.text[p:p + 1])

            try:
                return e.interactive_parser.resume_parse()
            except runtime.UnexpectedToken as e2:
                if (isinstance(e, runtime.UnexpectedToken)
                    and e.token.type == e2.token.type == "$END"
                        and e.interactive_parser == e2.interactive_parser):
                    # Prevent infinite loop
                    raise e2
                e = e2
            except runtime.UnexpectedCharacters as e2:
                e = e2

# }


cdef class Meta:

    cdef public bint empty
    cdef dict __dict__

    def __init__(self):
        self.empty = True


cdef class Tree:
    cdef public object data
    cdef public list children  # : 'List[Union[str, Tree]]'
    cdef public Meta _meta

    def __cinit__(self, data, list children, meta=None):
        self.data = data
        self.children = children
        self._meta = meta

    @property
    def meta(self) -> Meta:
        if self._meta is None:
            self._meta = Meta()
        return self._meta

    def __repr__(self):
        return "Tree(%r, %r)" % (self.data, self.children)

    def _pretty_label(self):
        return str(self.data)

    def _pretty(self, level, indent_str):
        if len(self.children) == 1 and not isinstance(self.children[0], Tree):
            return [
                indent_str * level, self._pretty_label(), "\t",
                "%s" % (self.children[0],), "\n",
            ]

        lines = [indent_str * level, self._pretty_label(), "\n"]
        for n in self.children:
            if isinstance(n, Tree):
                lines += n._pretty(level + 1, indent_str)
            else:
                lines += [indent_str * (level + 1), "%s" % (n,), "\n"]

        return lines

    def pretty(self, indent_str: str = "  ") -> str:
        """Returns an indented string representation of the tree.

        Great for debugging.
        """
        return "".join(self._pretty(0, indent_str))

    def __eq__(self, other):
        try:
            return self.data == other.data and self.children == other.children
        except AttributeError:
            return False

    def __ne__(self, other):
        return not (self == other)

    def __hash__(self) -> int:
        return hash((self.data, tuple(self.children)))

    def __lark_meta__(self):
        return self.meta

    def iter_subtrees(self) -> "Iterator[Tree]":
        """Depth-first iteration.

        Visit each subtree once, even when the parse tree is a DAG.
        """
        queue = [self]
        seen = {id(self)}
        for subtree in queue:
            for child in reversed(subtree.children):
                child_id = id(child)
                if isinstance(child, Tree) and child_id not in seen:
                    seen.add(child_id)
                    queue.append(child)

        return reversed(queue)

    def find_pred(self, pred: "Callable[[Tree], bool]") -> "Iterator[Tree]":
        """Returns all nodes of the tree that evaluate pred(node) as true."""
        return filter(pred, self.iter_subtrees())

    def find_data(self, data: str) -> "Iterator[Tree]":
        """Returns all nodes of the tree whose data equals the given data."""
        return self.find_pred(lambda t: t.data == data)

# }

    def expand_kids_by_data(self, *data_values):
        """Inline children with the given data values; report whether any changed."""
        changed = False
        for i in range(len(self.children) - 1, -1, -1):
            child = self.children[i]
            if isinstance(child, Tree) and child.data in data_values:
                self.children[i:i + 1] = child.children
                changed = True
        return changed

    def scan_values(self, pred: "Callable[[Union[str, Tree]], bool]") -> Iterator[str]:
        """Return all values in the tree that evaluate pred(value) as true.

        This can be used to find all the tokens in the tree.

        Example:
            >>> all_tokens = tree.scan_values(lambda v: isinstance(v, Token))
        """
        for c in self.children:
            if isinstance(c, Tree):
                for t in c.scan_values(pred):
                    yield t
            else:
                if pred(c):
                    yield c

    def iter_subtrees_topdown(self):
        """Breadth-first iteration.

        Iterates over all the subtrees, return nodes in order like pretty() does.
        """
        stack = [self]
        while stack:
            node = stack.pop()
            if not isinstance(node, Tree):
                continue
            yield node
            for n in reversed(node.children):
                stack.append(n)

    def __deepcopy__(self, memo):
        return type(self)(self.data, deepcopy(self.children, memo), meta=self._meta)

    def copy(self) -> Tree:
        return type(self)(self.data, self.children)

    def set(self, data: str, children: "List[Union[str, Tree]]") -> None:
        self.data = data
        self.children = children


#####


def apply_visit_wrapper(func, name, wrapper):
    if wrapper is _vargs_meta or wrapper is _vargs_meta_inline:
        raise NotImplementedError("Meta args not supported for internal transformer")

    @wraps(func)
    def f(children):
        return wrapper(func, name, children, None)
    return f


def inplace_transformer(func):
    @wraps(func)
    def f(list children):
        # function name in a Transformer is a rule name.
        cdef Tree tree
        tree = Tree(func.__name__, children)
        return func(tree)
    return f


cdef class ExpandSingleChild:
    cdef node_builder

    def __init__(self, node_builder):
        self.node_builder = node_builder

    def __call__(self, list children):
        if len(children) == 1:
            return children[0]
        else:
            return self.node_builder(children)


cdef class PropagatePositions:
    cdef node_builder
    cdef node_filter

    def __init__(self, node_builder, node_filter=None):
        self.node_builder = node_builder
        self.node_filter = node_filter

    def __call__(self, children):
        cdef Meta res_meta
        cdef object first_meta, last_meta

        res = self.node_builder(children)

        if isinstance(res, Tree):
            # Calculate positions while the tree is streaming, according to the rule:
            # - nodes start at the start of their first child's container,
            #   and end at the end of their last child's container.
            # Containers occupy text, but have been inlined in the tree.

            res_meta = res.meta

            first_meta = self._pp_get_meta(children)
            if first_meta is not None:
                if not hasattr(res_meta, "line"):
                    # An inlined rule (e.g. `?rule`) may already have set meta.
                    res_meta.line = getattr(
                        first_meta, "container_line", first_meta.line)
                    res_meta.column = getattr(
                        first_meta, "container_column", first_meta.column)
                    res_meta.start_pos = getattr(
                        first_meta, "container_start_pos", first_meta.start_pos)
                    res_meta.empty = False

                res_meta.container_line = getattr(
                    first_meta, "container_line", first_meta.line)
                res_meta.container_column = getattr(
                    first_meta, "container_column", first_meta.column)
                res_meta.container_start_pos = getattr(
                    first_meta, "container_start_pos", first_meta.start_pos)

            last_meta = self._pp_get_meta(reversed(children))
            if last_meta is not None:
                if not hasattr(res_meta, "end_line"):
                    res_meta.end_line = getattr(
                        last_meta, "container_end_line", last_meta.end_line)
                    res_meta.end_column = getattr(
                        last_meta, "container_end_column", last_meta.end_column)
                    res_meta.end_pos = getattr(
                        last_meta, "container_end_pos", last_meta.end_pos)
                    res_meta.empty = False

                res_meta.container_end_line = getattr(
                    last_meta, "container_end_line", last_meta.end_line)
                res_meta.container_end_column = getattr(
                    last_meta, "container_end_column", last_meta.end_column)
                res_meta.container_end_pos = getattr(
                    last_meta, "container_end_pos", last_meta.end_pos)

        return res

    cdef _pp_get_meta(self, children):
        for c in children:
            if self.node_filter is not None and not self.node_filter(c):
                continue
            if isinstance(c, Tree):
                if not c.meta.empty:
                    return c.meta
            elif isinstance(c, Token):
                return c

cdef make_propagate_positions(option):
    if callable(option):
        return partial(PropagatePositions, node_filter=option)
    elif option is True:
        return PropagatePositions
    elif option is False:
        return None

    raise ConfigurationError("Invalid option for propagate_positions: %r" % option)


cdef class ChildFilter:
    cdef readonly node_builder
    cdef readonly list to_include
    cdef readonly append_none

    def __init__(self, to_include, append_none, node_builder):
        self.node_builder = node_builder
        self.to_include = to_include
        self.append_none = append_none

    def __call__(self, children):
        filtered = []

        for i, to_expand, add_none in self.to_include:
            if add_none:
                filtered += [None] * add_none
            if to_expand:
                filtered += children[i].children
            else:
                filtered.append(children[i])

        if self.append_none:
            filtered += [None] * self.append_none

        return self.node_builder(filtered)


cdef class ChildFilterLALR(ChildFilter):
    """Filter LALR children in place, assuming no duplication in the parse tree."""

    def __call__(self, children):
        cdef int i
        cdef bint to_expand
        cdef int add_none
        cdef list filtered
        filtered = []
        for i, to_expand, add_none in self.to_include:
            if add_none:
                filtered += [None] * add_none
            if to_expand:
                if filtered:
                    filtered += children[i].children
                else:   # Optimize for left-recursion
                    filtered = children[i].children
            else:
                filtered.append(children[i])

        if self.append_none:
            filtered += [None] * self.append_none

        return self.node_builder(filtered)


cdef class ChildFilterLALR_NoPlaceholders(ChildFilter):
    """Filter LALR children in place, assuming no duplication in the parse tree."""

    def __init__(self, to_include, node_builder):
        self.node_builder = node_builder
        self.to_include = to_include

    def __call__(self, list children):
        cdef int i
        cdef bint to_expand
        cdef list filtered
        cdef Tree child
        filtered = []
        for i, to_expand in self.to_include:
            if to_expand:
                child = children[i]
                if filtered:
                    filtered += child.children
                else:   # Optimize for left-recursion
                    filtered = child.children
            else:
                filtered.append(children[i])
        return self.node_builder(filtered)


def _should_expand(sym):
    name = sym.name
    if not isinstance(name, str):
        name = name.value
    return not sym.is_term and name.startswith("_")


def maybe_create_child_filter(expansion, keep_all_tokens, ambiguous, _empty_indices):
    # Prepare empty_indices as: How many Nones to insert at each index?
    if _empty_indices:
        assert _empty_indices.count(False) == len(expansion)
        s = "".join(str(int(b)) for b in _empty_indices)
        empty_indices = [len(ones) for ones in s.split("0")]
        assert len(empty_indices) == len(expansion) + 1, (empty_indices, len(expansion))
    else:
        empty_indices = [0] * (len(expansion) + 1)

    to_include = []
    nones_to_add = 0
    for i, sym in enumerate(expansion):
        nones_to_add += empty_indices[i]
        if keep_all_tokens or not (sym.is_term and sym.filter_out):
            to_include.append((i, _should_expand(sym), nones_to_add))
            nones_to_add = 0

    nones_to_add += empty_indices[len(expansion)]

    if (
        _empty_indices
        or len(to_include) < len(expansion)
        or any(to_expand for _, to_expand, _ in to_include)
    ):
        if _empty_indices or ambiguous:
            return partial(
                ChildFilter if ambiguous else ChildFilterLALR,
                to_include, nones_to_add,
            )
        else:
            # LALR without placeholders
            return partial(
                ChildFilterLALR_NoPlaceholders,
                [(i, x) for i, x, _ in to_include],
            )


class ParseTreeBuilder:

    def __init__(
        self, rules, tree_class, propagate_positions=False, ambiguous=False,
        maybe_placeholders=False,
    ):
        self.tree_class = tree_class
        self.rule_builders = list(self._init_builders(
            rules, propagate_positions, ambiguous, maybe_placeholders,
        ))

    def _init_builders(
        self, rules, propagate_positions, ambiguous, maybe_placeholders,
    ):
        propagate_positions = make_propagate_positions(propagate_positions)

        for rule in rules:
            options = rule.options
            keep_all_tokens = options.keep_all_tokens
            expand_single_child = options.expand1

            wrapper_chain = list(filter(None, [
                (expand_single_child and not rule.alias) and ExpandSingleChild,
                maybe_create_child_filter(
                    rule.expansion, keep_all_tokens, ambiguous,
                    options.empty_indices if maybe_placeholders else None,
                ),
                propagate_positions,
            ]))

            yield rule, wrapper_chain

    def create_callback(self, transformer=None):
        callbacks = {}

        default_handler = getattr(transformer, "__default__", None)
        if default_handler:
            def default_callback(data, children):
                return default_handler(data, children, None)
        else:
            default_callback = self.tree_class

        for rule, wrapper_chain in self.rule_builders:

            user_callback_name = (
                rule.alias or rule.options.template_source or rule.origin.name
            )
            try:
                if not isinstance(user_callback_name, str):
                    user_callback_name = user_callback_name.value
                f = getattr(transformer, user_callback_name)
                wrapper = getattr(f, "visit_wrapper", None)
                if wrapper is not None:
                    f = apply_visit_wrapper(f, user_callback_name, wrapper)
                elif isinstance(transformer, Transformer_InPlace):
                    f = inplace_transformer(f)
            except AttributeError:
                f = partial(default_callback, user_callback_name)

            for w in wrapper_chain:
                f = w(f)

            if rule in callbacks:
                raise GrammarError("Rule '%s' already exists" % (rule,))

            callbacks[rule] = f

        return callbacks


plugins = {
    "BasicLexer": BasicLexer,
    "ContextualLexer": ContextualLexer,
    "LexerThread": LexerThread,
    "LALR_Parser": LALR_Parser,
    "_Parser": _Parser,     # XXX Ugly
}


_DEFAULT_RUNTIME = SimpleNamespace(
    Token=LarkToken, TerminalDef=TerminalDef,
    create_unless=_create_unless,
    LexError=LexError, UnexpectedInput=UnexpectedInput,
    UnexpectedToken=UnexpectedToken, UnexpectedCharacters=UnexpectedCharacters,
    InteractiveParser=InteractiveParser,
)
