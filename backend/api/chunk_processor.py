# backend/api/chunk_processor.py

"""
Code Chunking Processor
Converts AST data into semantic code chunks (functions, classes, methods)
Based on cAST research principles: respect syntactic boundaries
"""

import hashlib
from typing import Dict, Any, List


def generate_chunk_id(file_path: str, name: str, start_line: int) -> str:
    """Generate unique chunk ID: file_path::name::Lstart_line"""
    return f"{file_path}::{name}::L{start_line}"


def extract_function_body(file_content: str, function_name: str, start_line: int = 0) -> tuple:
    """
    Extract function body from file content
    Returns: (code, start_line, end_line)

    This is a heuristic-based approach that works for Python/JS
    For production: would use tree-sitter for precise extraction
    """
    lines = file_content.split('\n')

    # Find function definition line
    func_start = None
    for i, line in enumerate(lines):
        if function_name in line and ('def ' in line or 'function ' in line or 'const ' in line):
            func_start = i
            break

    if func_start is None:
        # Fallback: return empty
        return "", 0, 0

    # Extract function body by indentation or braces
    indent_level = len(lines[func_start]) - len(lines[func_start].lstrip())
    func_end = func_start

    # Check if using braces (JS/Java/etc)
    using_braces = '{' in lines[func_start]

    if using_braces:
        brace_count = lines[func_start].count('{') - lines[func_start].count('}')
        for i in range(func_start + 1, len(lines)):
            brace_count += lines[i].count('{') - lines[i].count('}')
            func_end = i
            if brace_count == 0:
                break
    else:
        # Python-style: indentation based
        for i in range(func_start + 1, len(lines)):
            line = lines[i]
            if line.strip() == '':
                continue
            current_indent = len(line) - len(line.lstrip())

            # Fix for multi-line signatures: '):' at indent=0 is end of signature, not function
            # The function body comes after this line
            if current_indent <= indent_level and line.strip() in ['):', ')']:
                func_end = i
                continue

            if current_indent <= indent_level:
                func_end = i - 1
                break
            func_end = i

    code = '\n'.join(lines[func_start:func_end + 1])
    return code, func_start + 1, func_end + 1  # +1 for 1-indexed lines


def extract_class_body(file_content: str, class_name: str) -> tuple:
    """
    Extract class body from file content
    Returns: (code, start_line, end_line)
    """
    lines = file_content.split('\n')

    # Find class definition
    class_start = None
    for i, line in enumerate(lines):
        if class_name in line and ('class ' in line):
            class_start = i
            break

    if class_start is None:
        return "", 0, 0

    indent_level = len(lines[class_start]) - len(lines[class_start].lstrip())
    class_end = class_start

    using_braces = '{' in lines[class_start]

    if using_braces:
        brace_count = lines[class_start].count('{') - lines[class_start].count('}')
        for i in range(class_start + 1, len(lines)):
            brace_count += lines[i].count('{') - lines[i].count('}')
            class_end = i
            if brace_count == 0:
                break
    else:
        for i in range(class_start + 1, len(lines)):
            line = lines[i]
            if line.strip() == '':
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= indent_level:
                class_end = i - 1
                break
            class_end = i

    code = '\n'.join(lines[class_start:class_end + 1])
    return code, class_start + 1, class_end + 1


def extract_module_variables(file_path: str, file_content: str, ast_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract module-level variables (STEPS, CONFIG, constants, etc.)

    Args:
        file_path: Path to file
        file_content: File content
        ast_info: AST info (for imports)

    Returns:
        List of module variable chunks
    """
    import ast as ast_module

    chunks = []

    # Only process Python files
    if not file_path.endswith('.py'):
        return chunks

    try:
        tree = ast_module.parse(file_content)
    except:
        return chunks

    # Extract module-level assignments (only top-level, not inside functions)
    # Use tree.body to get only module-level statements
    for node in tree.body:
        if isinstance(node, ast_module.Assign):
            # Get variable name
            for target in node.targets:
                if isinstance(target, ast_module.Name):
                    var_name = target.id

                    # Skip private variables and common non-config names
                    if var_name.startswith('_') or var_name in ['i', 'j', 'x', 'y', 'temp']:
                        continue

                    # Get value as string
                    try:
                        value_code = ast_module.unparse(node.value)
                    except:
                        value_code = "<complex value>"

                    # Get line number
                    lineno = node.lineno

                    # Format as code chunk
                    code = f"{var_name} = {value_code}"

                    chunk_id = generate_chunk_id(file_path, var_name, lineno)
                    chunks.append({
                        'chunk_id': chunk_id,
                        'file_path': file_path,
                        'type': 'module_variable',
                        'name': var_name,
                        'code': code,
                        'start_line': lineno,
                        'end_line': lineno,
                        'metadata': {
                            'imports': ast_info.get('imports', []),
                            'file_type': 'py',
                            'variable_type': type(node.value).__name__
                        }
                    })

    return chunks


def chunk_file(file_path: str, ast_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Convert file AST info into chunks

    Args:
        file_path: relative path to file
        ast_info: output from ast_parser (functions, classes, imports, content)

    Returns:
        List of chunk dictionaries
    """
    chunks = []
    file_content = ast_info.get('content', '')

    if not file_content:
        # No content, can't extract chunks
        return chunks

    # Extract function chunks
    for func_name in ast_info.get('functions', []):
        code, start_line, end_line = extract_function_body(file_content, func_name)

        if code:
            chunk_id = generate_chunk_id(file_path, func_name, start_line)
            chunks.append({
                'chunk_id': chunk_id,
                'file_path': file_path,
                'type': 'function',
                'name': func_name,
                'code': code,
                'start_line': start_line,
                'end_line': end_line,
                'metadata': {
                    'imports': ast_info.get('imports', []),
                    'file_type': file_path.split('.')[-1] if '.' in file_path else 'unknown'
                }
            })

    # Extract class chunks
    for class_name in ast_info.get('classes', []):
        code, start_line, end_line = extract_class_body(file_content, class_name)

        if code:
            chunk_id = generate_chunk_id(file_path, class_name, start_line)
            chunks.append({
                'chunk_id': chunk_id,
                'file_path': file_path,
                'type': 'class',
                'name': class_name,
                'code': code,
                'start_line': start_line,
                'end_line': end_line,
                'metadata': {
                    'imports': ast_info.get('imports', []),
                    'file_type': file_path.split('.')[-1] if '.' in file_path else 'unknown'
                }
            })

    # Extract module-level variables (STEPS, CONFIG, constants, etc.)
    # These are critical for understanding configuration and entry points
    module_vars = extract_module_variables(file_path, file_content, ast_info)

    # Only add module vars if we also have functions/classes (avoid duplication)
    # If file has ONLY variables and no functions, file-level chunk is better
    if ast_info.get('functions') or ast_info.get('classes'):
        chunks.extend(module_vars)

    # If no functions or classes found, create a file-level chunk
    # This handles config files, simple scripts, etc.
    if not chunks and file_content:
        chunk_id = generate_chunk_id(file_path, 'file_content', 1)
        chunks.append({
            'chunk_id': chunk_id,
            'file_path': file_path,
            'type': 'file',
            'name': file_path.split('/')[-1],
            'code': file_content,
            'start_line': 1,
            'end_line': len(file_content.split('\n')),
            'metadata': {
                'imports': ast_info.get('imports', []),
                'file_type': file_path.split('.')[-1] if '.' in file_path else 'unknown'
            }
        })

    return chunks


def process_repository_to_chunks(ast_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Convert entire repository AST data to chunks

    Args:
        ast_data: dict of {file_path: ast_info}

    Returns:
        List of all chunks across repository
    """
    all_chunks = []

    for file_path, ast_info in ast_data.items():
        file_chunks = chunk_file(file_path, ast_info)
        all_chunks.extend(file_chunks)

    return all_chunks


def validate_chunk(chunk: Dict[str, Any]) -> bool:
    """Validate chunk has required fields and sensible values"""
    required_fields = ['chunk_id', 'file_path', 'type', 'name', 'code',
                      'start_line', 'end_line', 'metadata']

    # Check all required fields present
    if not all(field in chunk for field in required_fields):
        return False

    # Check code is not empty
    if not chunk['code'].strip():
        return False

    # Check line numbers make sense
    if chunk['start_line'] <= 0 or chunk['end_line'] < chunk['start_line']:
        return False

    # Check code length is reasonable (not too small, not too large)
    code_length = len(chunk['code'])
    if code_length < 10 or code_length > 50000:  # 10 chars min, 50KB max
        return False

    return True


def get_chunk_stats(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Get statistics about chunks for debugging/validation"""
    if not chunks:
        return {'total': 0}

    stats = {
        'total': len(chunks),
        'by_type': {},
        'avg_lines': 0,
        'avg_chars': 0,
        'files_processed': len(set(c['file_path'] for c in chunks))
    }

    total_lines = 0
    total_chars = 0

    for chunk in chunks:
        chunk_type = chunk['type']
        stats['by_type'][chunk_type] = stats['by_type'].get(chunk_type, 0) + 1

        lines = chunk['end_line'] - chunk['start_line'] + 1
        total_lines += lines
        total_chars += len(chunk['code'])

    stats['avg_lines'] = total_lines / len(chunks)
    stats['avg_chars'] = total_chars / len(chunks)

    return stats
