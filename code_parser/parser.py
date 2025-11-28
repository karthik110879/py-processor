from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_typescript as tstypescript

# Load compiled grammar
PY_LANGUAGE = Language(tspython.language())
parser_py = Parser(PY_LANGUAGE)

# Load compiled grammar
TS_LANGUAGE = Language(tstypescript.language_typescript())
parser_ts = Parser(TS_LANGUAGE)

def parse_python(source: str):
    """Parse a Python file into a Tree-sitter syntax tree."""
    tree = parser_py.parse(bytes(source, "utf8"))
    return tree.root_node


def parse_typescript(source: str):
    """Parse a TypeScript file into a Tree-sitter syntax tree."""
    tree = parser_ts.parse(bytes(source, "utf8"))
    return tree.root_node