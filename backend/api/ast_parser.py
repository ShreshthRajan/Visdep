# dependency_extracton/backend/api/ast_parser.py
import os
import ast
import subprocess
import logging
from typing import Dict, Any
from bs4 import BeautifulSoup  # For HTML parsing
import clang.cindex  # For C/C++ parsing
import tempfile
import re
import javalang
import esprima

# Python AST Parsing
def parse_python_file(file_path: str) -> ast.AST:
    with open(file_path, 'r') as file:
        file_content = file.read()
    tree = ast.parse(file_content, filename=file_path)
    return tree

def extract_python_info(tree: ast.AST) -> Dict[str, Any]:
    """
    Extract structured Python code information with method-level granularity.

    Returns:
        {
            'functions': [{'name': 'func', 'lineno': 10, 'end_lineno': 25, ...}],
            'classes': [{'name': 'Session', 'lineno': 50, 'end_lineno': 200,
                        'methods': [{'name': 'request', 'lineno': 60, ...}]}],
            'imports': ['os', 'sys.path', ...]
        }
    """
    info = {
        "functions": [],
        "classes": [],
        "imports": []
    }

    # Use tree.body (not ast.walk) to preserve hierarchy and distinguish
    # top-level functions from class methods
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            # Top-level function
            info["functions"].append({
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": node.end_lineno if hasattr(node, 'end_lineno') else node.lineno,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "decorators": [ast.unparse(d) for d in node.decorator_list] if node.decorator_list else []
            })

        elif isinstance(node, ast.AsyncFunctionDef):
            # Top-level async function
            info["functions"].append({
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": node.end_lineno if hasattr(node, 'end_lineno') else node.lineno,
                "is_async": True,
                "decorators": [ast.unparse(d) for d in node.decorator_list] if node.decorator_list else []
            })

        elif isinstance(node, ast.ClassDef):
            # Class with structured method information
            methods = []
            class_docstring_lines = 0

            for item in node.body:
                if isinstance(item, ast.FunctionDef) or isinstance(item, ast.AsyncFunctionDef):
                    # Method within class
                    methods.append({
                        "name": item.name,
                        "lineno": item.lineno,
                        "end_lineno": item.end_lineno if hasattr(item, 'end_lineno') else item.lineno,
                        "is_async": isinstance(item, ast.AsyncFunctionDef),
                        "decorators": [ast.unparse(d) for d in item.decorator_list] if item.decorator_list else []
                    })
                elif isinstance(item, ast.Expr) and isinstance(item.value, ast.Constant):
                    # Class docstring (count lines for definition extraction)
                    if isinstance(item.value.value, str):
                        class_docstring_lines = len(item.value.value.split('\n'))

            info["classes"].append({
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": node.end_lineno if hasattr(node, 'end_lineno') else node.lineno,
                "methods": methods,
                "docstring_lines": class_docstring_lines,
                "decorators": [ast.unparse(d) for d in node.decorator_list] if node.decorator_list else [],
                "bases": [ast.unparse(base) for base in node.bases] if node.bases else []
            })

        elif isinstance(node, ast.Import):
            for alias in node.names:
                info["imports"].append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for alias in node.names:
                    info["imports"].append(f"{node.module}.{alias.name}")

    return info

# Tree-sitter imports (SOTA multi-language parsing - Nov 2025)
try:
    from tree_sitter_language_pack import get_language, get_parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    logging.warning("tree-sitter-language-pack not installed, falling back to legacy parsers")

# JavaScript AST Parsing (using tree-sitter - PHASE 1)
def parse_javascript_file_tree_sitter(file_path: str) -> Dict[str, Any]:
    """Parse JavaScript/TypeScript with tree-sitter (error-tolerant, handles modern syntax)"""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    # Detect TypeScript vs JavaScript
    is_typescript = file_path.endswith(('.ts', '.tsx'))
    language_name = 'typescript' if is_typescript else 'javascript'

    parser = get_parser(language_name)
    tree = parser.parse(bytes(content, 'utf8'))

    return {'tree': tree, 'content': content, 'language': language_name}

def extract_javascript_info_tree_sitter(parse_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract functions/classes from tree-sitter AST with method-level granularity (simplified tree walk)"""
    tree = parse_result['tree']
    content = parse_result['content']

    info = {
        "functions": [],
        "classes": [],
        "imports": []
    }

    def walk_node(node, parent_class=None):
        """Recursively walk tree to find functions and classes"""

        # Function declarations (top-level or within objects)
        if node.type == 'function_declaration':
            func_name = None
            for child in node.children:
                if child.type == 'identifier':
                    func_name = child.text.decode('utf8')
                    break

            if func_name and not parent_class:
                info["functions"].append({
                    "name": func_name,
                    "lineno": node.start_point[0] + 1,
                    "end_lineno": node.end_point[0] + 1,
                    "is_async": 'async' in node.text.decode('utf8')[:30],
                    "decorators": []
                })

        # Class declarations
        elif node.type == 'class_declaration':
            class_name = None
            class_body = None

            for child in node.children:
                if child.type in ('identifier', 'type_identifier'):  # TS uses type_identifier
                    class_name = child.text.decode('utf8')
                elif child.type == 'class_body':
                    class_body = child

            if class_name:
                methods = []

                # Extract methods from class body
                if class_body:
                    for child in class_body.children:
                        if child.type == 'method_definition':
                            method_name = None
                            for method_child in child.children:
                                if method_child.type == 'property_identifier':
                                    method_name = method_child.text.decode('utf8')
                                    break

                            if method_name:
                                methods.append({
                                    "name": method_name,
                                    "lineno": child.start_point[0] + 1,
                                    "end_lineno": child.end_point[0] + 1,
                                    "is_async": 'async' in child.text.decode('utf8')[:30],
                                    "decorators": []
                                })

                info["classes"].append({
                    "name": class_name,
                    "lineno": node.start_point[0] + 1,
                    "end_lineno": node.end_point[0] + 1,
                    "methods": methods,
                    "docstring_lines": 0,
                    "decorators": [],
                    "bases": []
                })

                # Don't recurse into class body for functions (already got methods)
                return

        # Import statements
        elif node.type == 'import_statement':
            for child in node.children:
                if child.type == 'string':
                    import_path = child.text.decode('utf8').strip('"\'')
                    info["imports"].append(import_path)

        # Recurse into children
        for child in node.children:
            walk_node(child, parent_class)

    walk_node(tree.root_node)

    # Add content for chunking
    info['content'] = content

    return info

# Java AST Parsing (using tree-sitter - PHASE 2)
def parse_java_file_tree_sitter(file_path: str) -> Dict[str, Any]:
    """Parse Java with tree-sitter (error-tolerant, handles all Java versions)"""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    parser = get_parser('java')
    tree = parser.parse(bytes(content, 'utf8'))

    return {'tree': tree, 'content': content}

def extract_java_info_tree_sitter(parse_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract Java functions/classes with method-level granularity"""
    tree = parse_result['tree']
    content = parse_result['content']

    info = {
        "functions": [],
        "classes": [],
        "imports": []
    }

    def walk_node(node):
        # Method declarations (outside classes) or functions
        if node.type == 'method_declaration':
            method_name = None
            for child in node.children:
                if child.type == 'identifier':
                    method_name = child.text.decode('utf8')
                    break

            if method_name:
                info["functions"].append({
                    "name": method_name,
                    "lineno": node.start_point[0] + 1,
                    "end_lineno": node.end_point[0] + 1,
                    "is_async": False,  # Java doesn't have async keyword
                    "decorators": []
                })

        # Class declarations
        elif node.type == 'class_declaration':
            class_name = None
            class_body = None

            for child in node.children:
                if child.type == 'identifier':
                    class_name = child.text.decode('utf8')
                elif child.type == 'class_body':
                    class_body = child

            if class_name:
                methods = []

                # Extract methods from class body
                if class_body:
                    for child in class_body.children:
                        if child.type == 'method_declaration':
                            method_name = None
                            for method_child in child.children:
                                if method_child.type == 'identifier':
                                    method_name = method_child.text.decode('utf8')
                                    break

                            if method_name:
                                methods.append({
                                    "name": method_name,
                                    "lineno": child.start_point[0] + 1,
                                    "end_lineno": child.end_point[0] + 1,
                                    "is_async": False,
                                    "decorators": []
                                })

                info["classes"].append({
                    "name": class_name,
                    "lineno": node.start_point[0] + 1,
                    "end_lineno": node.end_point[0] + 1,
                    "methods": methods,
                    "docstring_lines": 0,
                    "decorators": [],
                    "bases": []
                })

        # Import statements
        elif node.type == 'import_declaration':
            for child in node.children:
                if child.type == 'scoped_identifier':
                    import_path = child.text.decode('utf8')
                    info["imports"].append(import_path)

        # Recurse
        for child in node.children:
            walk_node(child)

    walk_node(tree.root_node)
    info['content'] = content
    return info

# Go AST Parsing (using tree-sitter - PHASE 2)
def parse_go_file_tree_sitter(file_path: str) -> Dict[str, Any]:
    """Parse Go with tree-sitter (error-tolerant, handles all Go versions)"""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    parser = get_parser('go')
    tree = parser.parse(bytes(content, 'utf8'))

    return {'tree': tree, 'content': content}

def extract_go_info_tree_sitter(parse_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract Go functions/methods with granularity"""
    tree = parse_result['tree']
    content = parse_result['content']

    info = {
        "functions": [],
        "classes": [],  # Go doesn't have classes, but has types with methods
        "imports": []
    }

    def walk_node(node):
        # Function declarations
        if node.type == 'function_declaration':
            func_name = None
            for child in node.children:
                if child.type == 'identifier':
                    func_name = child.text.decode('utf8')
                    break

            if func_name:
                info["functions"].append({
                    "name": func_name,
                    "lineno": node.start_point[0] + 1,
                    "end_lineno": node.end_point[0] + 1,
                    "is_async": False,  # Go uses goroutines, not async keyword
                    "decorators": []
                })

        # Method declarations (functions with receivers)
        elif node.type == 'method_declaration':
            method_name = None
            receiver_type = None

            # Extract method name and receiver type
            receiver_found = False
            for child in node.children:
                if child.type == 'field_identifier':
                    method_name = child.text.decode('utf8')
                elif child.type == 'parameter_list' and not receiver_found:
                    # First parameter_list is the receiver (e.g., "(p Person)" or "(p *Person)")
                    receiver_found = True
                    receiver_text = child.text.decode('utf8').strip('()')

                    # Parse receiver: "p Person" or "p *Person"
                    parts = receiver_text.split()
                    if len(parts) >= 2:
                        # parts[0] is variable name (p), parts[1] is type (Person or *Person)
                        receiver_type = parts[1].lstrip('*')  # Remove pointer prefix

            if method_name and receiver_type:
                # Find or create the struct entry
                existing_class = None
                for cls in info["classes"]:
                    if cls["name"] == receiver_type:
                        existing_class = cls
                        break

                if not existing_class:
                    existing_class = {
                        "name": receiver_type,
                        "lineno": node.start_point[0] + 1,
                        "end_lineno": node.end_point[0] + 1,
                        "methods": [],
                        "docstring_lines": 0,
                        "decorators": [],
                        "bases": []
                    }
                    info["classes"].append(existing_class)

                existing_class["methods"].append({
                    "name": method_name,
                    "lineno": node.start_point[0] + 1,
                    "end_lineno": node.end_point[0] + 1,
                    "is_async": False,
                    "decorators": []
                })

        # Import statements
        elif node.type == 'import_declaration':
            for child in node.children:
                if child.type == 'import_spec_list':
                    for spec in child.children:
                        if spec.type == 'import_spec':
                            import_path = spec.text.decode('utf8')
                            info["imports"].append(import_path)

        # Recurse
        for child in node.children:
            walk_node(child)

    walk_node(tree.root_node)
    info['content'] = content
    return info

# C++ AST Parsing (using tree-sitter - PHASE 3)
def parse_cpp_file_tree_sitter(file_path: str) -> Dict[str, Any]:
    """Parse C++ with tree-sitter (error-tolerant, handles modern C++)"""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    parser = get_parser('cpp')
    tree = parser.parse(bytes(content, 'utf8'))

    return {'tree': tree, 'content': content}

def extract_cpp_info_tree_sitter(parse_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract C++ functions/classes with method-level granularity"""
    tree = parse_result['tree']
    content = parse_result['content']

    info = {
        "functions": [],
        "classes": [],
        "imports": []
    }

    def walk_node(node):
        # Function definitions (global functions)
        if node.type == 'function_definition':
            func_name = None
            for child in node.children:
                if child.type == 'function_declarator':
                    for declarator_child in child.children:
                        if declarator_child.type == 'identifier':
                            func_name = declarator_child.text.decode('utf8')
                            break
                    break

            if func_name:
                info["functions"].append({
                    "name": func_name,
                    "lineno": node.start_point[0] + 1,
                    "end_lineno": node.end_point[0] + 1,
                    "is_async": False,
                    "decorators": []
                })

        # Class/struct specifiers
        elif node.type in ('class_specifier', 'struct_specifier'):
            class_name = None
            class_body = None

            for child in node.children:
                if child.type == 'type_identifier':
                    class_name = child.text.decode('utf8')
                elif child.type == 'field_declaration_list':
                    class_body = child

            if class_name:
                methods = []

                # Extract methods from class body
                if class_body:
                    for child in class_body.children:
                        if child.type == 'function_definition':
                            method_name = None
                            for method_child in child.children:
                                if method_child.type == 'function_declarator':
                                    for decl_child in method_child.children:
                                        if decl_child.type == 'identifier' or decl_child.type == 'field_identifier':
                                            method_name = decl_child.text.decode('utf8')
                                            break
                                    break

                            if method_name:
                                methods.append({
                                    "name": method_name,
                                    "lineno": child.start_point[0] + 1,
                                    "end_lineno": child.end_point[0] + 1,
                                    "is_async": False,
                                    "decorators": []
                                })

                info["classes"].append({
                    "name": class_name,
                    "lineno": node.start_point[0] + 1,
                    "end_lineno": node.end_point[0] + 1,
                    "methods": methods,
                    "docstring_lines": 0,
                    "decorators": [],
                    "bases": []
                })

        # Include directives (#include)
        elif node.type == 'preproc_include':
            for child in node.children:
                if child.type in ('string_literal', 'system_lib_string'):
                    include_path = child.text.decode('utf8').strip('<>"')
                    info["imports"].append(include_path)

        # Recurse
        for child in node.children:
            walk_node(child)

    walk_node(tree.root_node)
    info['content'] = content
    return info

# Rust AST Parsing (using tree-sitter - PHASE 3)
def parse_rust_file_tree_sitter(file_path: str) -> Dict[str, Any]:
    """Parse Rust with tree-sitter (error-tolerant, handles Rust 2024)"""
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()

    parser = get_parser('rust')
    tree = parser.parse(bytes(content, 'utf8'))

    return {'tree': tree, 'content': content}

def extract_rust_info_tree_sitter(parse_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract Rust functions/methods with granularity"""
    tree = parse_result['tree']
    content = parse_result['content']

    info = {
        "functions": [],
        "classes": [],  # Rust uses structs/enums with impl blocks
        "imports": []
    }

    def walk_node(node):
        # Function items (standalone functions)
        if node.type == 'function_item':
            func_name = None
            for child in node.children:
                if child.type == 'identifier':
                    func_name = child.text.decode('utf8')
                    break

            if func_name:
                info["functions"].append({
                    "name": func_name,
                    "lineno": node.start_point[0] + 1,
                    "end_lineno": node.end_point[0] + 1,
                    "is_async": 'async' in node.text.decode('utf8')[:30],
                    "decorators": []
                })

        # Impl blocks (methods for structs/enums)
        elif node.type == 'impl_item':
            impl_type = None
            impl_body = None

            for child in node.children:
                if child.type == 'type_identifier':
                    impl_type = child.text.decode('utf8')
                elif child.type == 'declaration_list':
                    impl_body = child

            if impl_type:
                # Find or create struct entry
                existing_class = None
                for cls in info["classes"]:
                    if cls["name"] == impl_type:
                        existing_class = cls
                        break

                if not existing_class:
                    existing_class = {
                        "name": impl_type,
                        "lineno": node.start_point[0] + 1,
                        "end_lineno": node.end_point[0] + 1,
                        "methods": [],
                        "docstring_lines": 0,
                        "decorators": [],
                        "bases": []
                    }
                    info["classes"].append(existing_class)

                # Extract functions from impl block
                if impl_body:
                    for child in impl_body.children:
                        if child.type == 'function_item':
                            method_name = None
                            for func_child in child.children:
                                if func_child.type == 'identifier':
                                    method_name = func_child.text.decode('utf8')
                                    break

                            if method_name:
                                existing_class["methods"].append({
                                    "name": method_name,
                                    "lineno": child.start_point[0] + 1,
                                    "end_lineno": child.end_point[0] + 1,
                                    "is_async": 'async' in child.text.decode('utf8')[:30],
                                    "decorators": []
                                })

        # Use declarations
        elif node.type == 'use_declaration':
            use_text = node.text.decode('utf8')
            # Extract the path from "use std::collections::HashMap;"
            if 'use ' in use_text:
                import_path = use_text.replace('use ', '').strip(';').strip()
                info["imports"].append(import_path)

        # Recurse
        for child in node.children:
            walk_node(child)

    walk_node(tree.root_node)
    info['content'] = content
    return info

# JavaScript AST Parsing (using esprima - LEGACY FALLBACK)
def parse_javascript_file(file_path: str) -> Dict:
    with open(file_path, 'r') as file:
        content = file.read()
    return esprima.parseModule(content, {'jsx': True, 'tokens': True})

def extract_javascript_info(parsed_data: esprima.nodes.Module) -> Dict[str, Any]:
    info = {
        "functions": [],
        "classes": [],
        "imports": []
    }
    
    for node in parsed_data.body:
        if isinstance(node, esprima.nodes.FunctionDeclaration):
            info["functions"].append(node.id.name)
        elif isinstance(node, esprima.nodes.ClassDeclaration):
            info["classes"].append(node.id.name)
        elif isinstance(node, esprima.nodes.ImportDeclaration):
            if node.source.value:
                info["imports"].append(node.source.value)
    
    return info

# Java AST Parsing (using javaparser)
def parse_java_file(file_path: str) -> Dict:
    with open(file_path, 'r') as file:
        content = file.read()
    return javalang.parse.parse(content)

def extract_java_info(parsed_data: javalang.tree.CompilationUnit) -> Dict[str, Any]:
    info = {
        "functions": [],
        "classes": [],
        "imports": []
    }
    
    for path, node in parsed_data.filter(javalang.tree.MethodDeclaration):
        info["functions"].append(node.name)
    
    for path, node in parsed_data.filter(javalang.tree.ClassDeclaration):
        info["classes"].append(node.name)
    
    for imp in parsed_data.imports:
        info["imports"].append(imp.path)
    
    return info

# Go AST Parsing
def parse_go_file(file_path: str) -> Dict:
    with open(file_path, 'r') as file:
        content = file.read()
    return content

def extract_go_info(parsed_data: str) -> Dict[str, Any]:
    info = {
        "functions": [],
        "imports": []
    }
    
    # Extract imports
    import_pattern = r'import\s*\(([\s\S]*?)\)|import\s*([^\n]+)'
    imports = re.findall(import_pattern, parsed_data)
    
    for imp in imports:
        if imp[0]:  # Multi-line import
            packages = re.findall(r'"([^"]+)"', imp[0])
            info["imports"].extend(packages)
        elif imp[1]:  # Single-line import
            package = re.search(r'"([^"]+)"', imp[1])
            if package:
                info["imports"].append(package.group(1))
    
    # Extract functions (simplified, might need improvement)
    func_pattern = r'func\s+(\w+)'
    functions = re.findall(func_pattern, parsed_data)
    info["functions"] = functions
    
    return info

# C/C++ AST Parsing using clang
def parse_cpp_file(file_path: str) -> clang.cindex.TranslationUnit:
    index = clang.cindex.Index.create()
    tu = index.parse(file_path)
    return tu

def extract_cpp_info(tu: clang.cindex.TranslationUnit) -> Dict[str, Any]:
    info = {
        "functions": [],
        "classes": [],
        "imports": []
    }

    for node in tu.cursor.get_children():
        if node.kind == clang.cindex.CursorKind.FUNCTION_DECL:
            info["functions"].append(node.spelling)
        elif node.kind == clang.cindex.CursorKind.CLASS_DECL:
            info["classes"].append(node.spelling)
        elif node.kind == clang.cindex.CursorKind.INCLUSION_DIRECTIVE:
            included_file = node.get_included_file()
            if included_file:
                info["imports"].append(included_file.name)

    return info

# HTML Parsing
def parse_html_file(file_path: str) -> BeautifulSoup:
    with open(file_path, 'r') as file:
        file_content = file.read()
    soup = BeautifulSoup(file_content, 'html.parser')
    return soup

def extract_html_info(soup: BeautifulSoup) -> Dict[str, Any]:
    info = {
        "tags": [tag.name for tag in soup.find_all()]
    }
    return info

# SQL Parsing
def parse_sql_file(file_path: str) -> str:
    with open(file_path, 'r') as file:
        file_content = file.read()
    return file_content

def extract_sql_info(sql_content: str) -> Dict[str, Any]:
    info = {
        "queries": sql_content.split(';')
    }
    return info

# Handling Non-Code Files
def handle_non_code_file(file_path: str) -> Dict[str, Any]:
    return {
        "type": "non-code",
        "name": os.path.basename(file_path),
        "size": os.path.getsize(file_path)
    }

# Generic file parser
def parse_code_file(file_path: str) -> Dict[str, Any]:
    file_extension = os.path.splitext(file_path)[1].lower()
    try:
        if file_extension == '.py':
            tree = parse_python_file(file_path)
            return extract_python_info(tree)
        elif file_extension in ['.js', '.jsx', '.ts', '.tsx']:
            # PHASE 1: Use tree-sitter for JS/TS (SOTA, error-tolerant)
            if TREE_SITTER_AVAILABLE:
                parsed_data = parse_javascript_file_tree_sitter(file_path)
                return extract_javascript_info_tree_sitter(parsed_data)
            else:
                # Fallback to esprima if tree-sitter not available
                parsed_data = parse_javascript_file(file_path)
                return extract_javascript_info(parsed_data)
        elif file_extension == '.java':
            # PHASE 2: Use tree-sitter for Java (error-tolerant, robust)
            if TREE_SITTER_AVAILABLE:
                parsed_data = parse_java_file_tree_sitter(file_path)
                return extract_java_info_tree_sitter(parsed_data)
            else:
                # Fallback to javalang
                parsed_data = parse_java_file(file_path)
                return extract_java_info(parsed_data)
        elif file_extension == '.go':
            # PHASE 2: Use tree-sitter for Go (FINALLY IMPLEMENTED!)
            if TREE_SITTER_AVAILABLE:
                parsed_data = parse_go_file_tree_sitter(file_path)
                return extract_go_info_tree_sitter(parsed_data)
            else:
                # Old Go parser didn't work anyway
                parsed_data = parse_go_file(file_path)
                return extract_go_info(parsed_data)
        elif file_extension in ['.c', '.cpp', '.h', '.hpp']:
            # PHASE 3: Use tree-sitter for C++ (error-tolerant, modern C++ support)
            if TREE_SITTER_AVAILABLE:
                parsed_data = parse_cpp_file_tree_sitter(file_path)
                return extract_cpp_info_tree_sitter(parsed_data)
            else:
                # Fallback to clang (requires libclang installed)
                tu = parse_cpp_file(file_path)
                return extract_cpp_info(tu)
        elif file_extension == '.rs':
            # PHASE 3: Use tree-sitter for Rust (error-tolerant, Rust 2024 support)
            if TREE_SITTER_AVAILABLE:
                parsed_data = parse_rust_file_tree_sitter(file_path)
                return extract_rust_info_tree_sitter(parsed_data)
            else:
                # No legacy Rust parser available
                return handle_non_code_file(file_path)
        elif file_extension == '.html':
            soup = parse_html_file(file_path)
            return extract_html_info(soup)
        elif file_extension == '.sql':
            sql_content = parse_sql_file(file_path)
            return extract_sql_info(sql_content)
        else:
            return handle_non_code_file(file_path)
    except Exception as e:
        # PHASE 1: Robust error handling - create fallback chunk from full file
        logging.warning(f"Parser error for {file_path}: {e}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {
                "functions": [],
                "classes": [],
                "imports": [],
                "content": content,
                "error": str(e),
                "fallback": "full_file"  # Flag for chunking to create single chunk
            }
        except Exception as read_error:
            return {"error": str(e), "read_error": str(read_error)}

def traverse_directory(directory_path: str) -> Dict[str, Any]:
    ast_data = {}

    for root, _, files in os.walk(directory_path):
        for file in files:
            file_path = os.path.join(root, file)
            file_info = parse_code_file(file_path)
            ast_data[file_path] = file_info

    return ast_data

def parse_code_to_ast(repo_content: Dict[str, Any]) -> Dict[str, Any]:
    repo_path = download_repo_content(repo_content)
    ast_data = traverse_directory(repo_path)

    updated_ast_data = {}
    for file_path, info in ast_data.items():
        relative_path = os.path.relpath(file_path, repo_path)
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
        info['content'] = file_content
        updated_ast_data[relative_path] = info

    return updated_ast_data


def download_repo_content(repo_content: Dict[str, Any]) -> str:
    """
    Download the repository content to a local directory.
    This function assumes repo_content is a list of files with 'path' and 'content' keys.
    """
    repo_path = tempfile.mkdtemp()  # Use a temporary directory for testing
    os.makedirs(repo_path, exist_ok=True)

    for file in repo_content:
        file_path = os.path.join(repo_path, file['path'])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:  
            f.write(file['content'])  
    
    return repo_path
