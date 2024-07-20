import os
import ast
import subprocess
from typing import Dict, Any
from bs4 import BeautifulSoup  # For HTML parsing
import clang.cindex  # For C/C++ parsing

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
    result = subprocess.run(['esprima', '-t', file_path], capture_output=True, text=True)
    return result.stdout

def extract_javascript_info(parsed_data: str) -> Dict[str, Any]:
    # Implement extraction logic for JavaScript
    return {
        "functions": [],
        "classes": [],
        "imports": []
    }

# Java AST Parsing (using javaparser)
def parse_java_file(file_path: str) -> Dict:
    result = subprocess.run(['javaparser', file_path], capture_output=True, text=True)
    return result.stdout

def extract_java_info(parsed_data: str) -> Dict[str, Any]:
    # Implement extraction logic for Java
    return {
        "functions": [],
        "classes": [],
        "imports": []
    }

# Go AST Parsing
def parse_go_file(file_path: str) -> Dict:
    result = subprocess.run(['go', 'vet', '-json', file_path], capture_output=True, text=True)
    return result.stdout

def extract_go_info(parsed_data: str) -> Dict[str, Any]:
    # Implement extraction logic for Go
    return {
        "functions": [],
        "classes": [],
        "imports": []
    }

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
        elif node.kind == clang.cindex.CursorKind.INCLUDE_DIRECTIVE:
            info["imports"].append(node.spelling)

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
    file_extension = file_path.split('.')[-1]
    if file_extension == 'py':
        tree = parse_python_file(file_path)
        return extract_python_info(tree)
    elif file_extension in ['js', 'jsx']:
        parsed_data = parse_javascript_file(file_path)
        return extract_javascript_info(parsed_data)
    elif file_extension == 'java':
        parsed_data = parse_java_file(file_path)
        return extract_java_info(parsed_data)
    elif file_extension == 'go':
        parsed_data = parse_go_file(file_path)
        return extract_go_info(parsed_data)
    elif file_extension in ['c', 'cpp', 'h', 'hpp']:
        tu = parse_cpp_file(file_path)
        return extract_cpp_info(tu)
    elif file_extension == 'html':
        soup = parse_html_file(file_path)
        return extract_html_info(soup)
    elif file_extension == 'sql':
        sql_content = parse_sql_file(file_path)
        return extract_sql_info(sql_content)
    else:
        return handle_non_code_file(file_path)

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
    return ast_data

def download_repo_content(repo_content: Dict[str, Any]) -> str:
    """
    Download the repository content to a local directory.
    This function assumes repo_content is a list of files with 'path' and 'content' keys.
    """
    repo_path = "/path/to/local/repo"  # Set the path to download the repository content
    os.makedirs(repo_path, exist_ok=True)

    for file in repo_content:
        file_path = os.path.join(repo_path, file['path'])
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w') as f:
            f.write(file['content'])
    
    return repo_path