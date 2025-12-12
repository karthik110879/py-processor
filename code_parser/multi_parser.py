"""Multi-language parser using tree-sitter for various programming languages."""

import os
from typing import Optional
from tree_sitter import Language, Parser, Node
from code_parser.exceptions import ParseError

try:
    import tree_sitter_python as tspython
    PY_LANGUAGE = Language(tspython.language())
    parser_py = Parser(PY_LANGUAGE)
except ImportError:
    PY_LANGUAGE = None
    parser_py = None

try:
    import tree_sitter_typescript as tstypescript
    TS_LANGUAGE = Language(tstypescript.language_typescript())
    parser_ts = Parser(TS_LANGUAGE)
except ImportError:
    TS_LANGUAGE = None
    parser_ts = None

try:
    import tree_sitter_javascript as tsjavascript
    JS_LANGUAGE = Language(tsjavascript.language())
    parser_js = Parser(JS_LANGUAGE)
except ImportError:
    JS_LANGUAGE = None
    parser_js = None

try:
    import tree_sitter_java as tsjava
    JAVA_LANGUAGE = Language(tsjava.language())
    parser_java = Parser(JAVA_LANGUAGE)
except ImportError:
    JAVA_LANGUAGE = None
    parser_java = None

try:
    import tree_sitter_c as tsc
    C_LANGUAGE = Language(tsc.language())
    parser_c = Parser(C_LANGUAGE)
except ImportError:
    C_LANGUAGE = None
    parser_c = None

try:
    import tree_sitter_cpp as tscpp
    CPP_LANGUAGE = Language(tscpp.language())
    parser_cpp = Parser(CPP_LANGUAGE)
except ImportError:
    CPP_LANGUAGE = None
    parser_cpp = None

try:
    import tree_sitter_c_sharp as tscsharp
    CSHARP_LANGUAGE = Language(tscsharp.language())
    parser_csharp = Parser(CSHARP_LANGUAGE)
except ImportError:
    CSHARP_LANGUAGE = None
    parser_csharp = None


def detect_language(file_path: str) -> Optional[str]:
    """
    Detect programming language from file extension.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Language name or None if not supported
    """
    ext = os.path.splitext(file_path)[1].lower()
    
    language_map = {
        '.py': 'python',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.java': 'java',
        '.c': 'c',
        '.cpp': 'cpp',
        '.cc': 'cpp',
        '.cxx': 'cpp',
        '.h': 'c',
        '.hpp': 'cpp',
        '.hxx': 'cpp',
        '.cs': 'csharp',
        '.asp': 'asp',
        '.aspx': 'aspx',
    }
    
    return language_map.get(ext)


def parse_file(file_path: str) -> Optional[Node]:
    """
    Parse a file using the appropriate tree-sitter parser.
    
    Args:
        file_path: Path to the file to parse
        
    Returns:
        Root node of the AST or None if parsing fails or language not supported
    """
    language = detect_language(file_path)
    
    if not language:
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            source = f.read()
    except FileNotFoundError:
        raise ParseError(f"File not found: {file_path}", file_path=file_path)
    except (IOError, OSError) as e:
        raise ParseError(f"Failed to read file: {e}", file_path=file_path)
    
    # Select parser based on language
    parser = None
    
    if language == 'python' and parser_py:
        parser = parser_py
    elif language == 'typescript' and parser_ts:
        parser = parser_ts
    elif language == 'javascript' and parser_js:
        parser = parser_js
    elif language == 'java' and parser_java:
        parser = parser_java
    elif language == 'c' and parser_c:
        parser = parser_c
    elif language in ('cpp', 'cxx', 'cc') and parser_cpp:
        parser = parser_cpp
    elif language == 'csharp' and parser_csharp:
        parser = parser_csharp
    elif language in ('asp', 'aspx'):
        # Classic ASP/ASPX - not supported by tree-sitter, return None
        # Will be handled by regex-based parser in normalizer
        return None
    
    if parser:
        try:
            tree = parser.parse(bytes(source, 'utf8'))
            return tree.root_node
        except Exception:
            return None
    
    return None


def parse_source(source: str, language: str) -> Optional[Node]:
    """
    Parse source code string directly.
    
    Args:
        source: Source code string
        language: Language name ('python', 'typescript', 'javascript', 'java', 'c', 'cpp', 'csharp')
        
    Returns:
        Root node of the AST or None if parsing fails
    """
    parser = None
    
    if language == 'python' and parser_py:
        parser = parser_py
    elif language == 'typescript' and parser_ts:
        parser = parser_ts
    elif language == 'javascript' and parser_js:
        parser = parser_js
    elif language == 'java' and parser_java:
        parser = parser_java
    elif language == 'c' and parser_c:
        parser = parser_c
    elif language == 'cpp' and parser_cpp:
        parser = parser_cpp
    elif language == 'csharp' and parser_csharp:
        parser = parser_csharp
    
    if parser:
        try:
            tree = parser.parse(bytes(source, 'utf8'))
            return tree.root_node
        except Exception:
            return None
    
    return None

