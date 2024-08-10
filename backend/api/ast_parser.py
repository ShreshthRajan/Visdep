# dependency_extracton/backend/api/ast_parser.py
import os
import ast
import subprocess
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
    info = {
        "functions": [],
        "classes": [],
        "imports": []
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            info["functions"].append(node.name)
        elif isinstance(node, ast.ClassDef):
            info["classes"].append(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                info["imports"].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                info["imports"].append(f"{node.module}.{alias.name}")
    
    return info

# JavaScript AST Parsing (using esprima)
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
            parsed_data = parse_javascript_file(file_path)
            return extract_javascript_info(parsed_data)
        elif file_extension == '.java':
            parsed_data = parse_java_file(file_path)
            return extract_java_info(parsed_data)
        elif file_extension == '.go':
            parsed_data = parse_go_file(file_path)
            return extract_go_info(parsed_data)
        elif file_extension in ['.c', '.cpp', '.h', '.hpp']:
            tu = parse_cpp_file(file_path)
            return extract_cpp_info(tu)
        elif file_extension == '.html':
            soup = parse_html_file(file_path)
            return extract_html_info(soup)
        elif file_extension == '.sql':
            sql_content = parse_sql_file(file_path)
            return extract_sql_info(sql_content)
        else:
            return handle_non_code_file(file_path)
    except Exception as e:
        return {"error": str(e)}

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
