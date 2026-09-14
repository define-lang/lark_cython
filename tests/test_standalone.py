import io
import sys
from types import ModuleType
from uuid import uuid4

import pytest
from lark import Lark
from lark.tools.standalone import gen_standalone
from lark_cython import Token, standalone_plugins


def generate(grammar, lexer="contextual"):
    source = io.StringIO()
    gen_standalone(Lark(grammar, parser="lalr", lexer=lexer), out=source)
    module = ModuleType("generated_" + uuid4().hex)
    sys.modules[module.__name__] = module
    exec(compile(source.getvalue(), "<generated parser>", "exec"), module.__dict__)
    return module


@pytest.fixture(params=["basic", "contextual"])
def module(request):
    return generate('start: "if" NAME INT\n%import common.CNAME -> NAME\n%import common.INT\n%ignore " "', request.param)


def test_tokens_and_positions(module):
    parser = module.Lark_StandAlone(_plugins=standalone_plugins(module))
    result = parser.parse("if name 123")
    assert type(result) is module.Tree
    name, number = result.children
    assert isinstance(name, Token)
    assert name.value == "name"
    assert name.start_pos == 3
    assert name.end_pos == 7
    assert number.value == "123"
    assert number.start_pos == 8
    assert number.end_pos == 11


def test_generated_exception_classes(module):
    parser = module.Lark_StandAlone(_plugins=standalone_plugins(module))
    with pytest.raises(module.UnexpectedToken) as caught:
        parser.parse("if name name")
    assert caught.value.accepts == {"INT"}
    with pytest.raises(module.UnexpectedCharacters) as caught:
        parser.parse("if ?")
    assert caught.value.pos_in_stream == 3


def test_interactive_generated_token(module):
    parser = module.Lark_StandAlone(_plugins=standalone_plugins(module))
    cursor = parser.parse_interactive("if name")
    cursor.exhaust_lexer()
    assert cursor.accepts() == {"INT"}
    cursor.feed_token(module.Token("INT", "123"))
    name, number = cursor.feed_eof().children
    assert name.value == "name"
    assert number.value == "123"


def test_copy_resumes_independently(module):
    parser = module.Lark_StandAlone(_plugins=standalone_plugins(module))
    cursor = parser.parse_interactive("if name 123")
    cursor.feed_token(next(cursor.iter_parse()))
    duplicate = cursor.copy()
    assert duplicate.resume_parse() == cursor.resume_parse()


def test_generated_callback_token(module):
    def uppercase(token):
        return module.Token.new_borrow_pos("NAME", token.value.upper(), token)
    parser = module.Lark_StandAlone(_plugins=standalone_plugins(module),
                                  lexer_callbacks={"NAME": uppercase})
    token = parser.parse("if name 123").children[0]
    assert token.value == "NAME"
    assert token.start_pos == 3
    assert token.end_pos == 7


def test_recovery(module):
    positions = []
    def recover(error):
        assert isinstance(error, module.UnexpectedCharacters)
        positions.append(error.pos_in_stream)
        return True
    parser = module.Lark_StandAlone(_plugins=standalone_plugins(module))
    result = parser.parse("if ?! name 123", on_error=recover)
    assert result.children[0].value == "name"
    assert positions == [3, 4]


def test_transformer_lookahead_and_empty_rules():
    module = generate('start: item "a"\nitem:')
    calls = []
    class Reduce(module.Transformer):
        def item(self, children):
            calls.append("item")
            return 42
    parser = module.Lark_StandAlone(_plugins=standalone_plugins(module),
                                  transformer=Reduce())
    cursor = parser.parse_interactive("a")
    assert cursor.accepts() == {"A"}
    assert calls == []
    assert cursor.resume_parse() == module.Tree("start", [42])
    assert calls == ["item"]


def test_modules_keep_separate_exception_classes():
    first = generate('start: "a"')
    second = generate('start: "b"')
    parser = first.Lark_StandAlone(_plugins=standalone_plugins(first))
    other = second.Lark_StandAlone(_plugins=standalone_plugins(second))
    assert other.parse("b") == second.Tree("start", [])
    with pytest.raises(first.UnexpectedCharacters) as caught:
        parser.parse("?")
    assert not isinstance(caught.value, second.UnexpectedCharacters)
