# backend/api/chunk_processor.py

"""
Code Chunking Processor
Converts AST data into semantic code chunks (functions, classes, methods)
Based on cAST research principles: respect syntactic boundaries

UPDATED: Method-level chunking for optimal retrieval (50-800 tokens per chunk)
"""

import hashlib
from typing import Dict, Any, List
import tiktoken
import logging

# Initialize tiktoken encoder for accurate token counting
try:
    TOKEN_ENCODER = tiktoken.encoding_for_model("gpt-4")
except Exception:
    TOKEN_ENCODER = None
    logging.warning("Tiktoken not available, falling back to character-based estimation")


def generate_chunk_id(file_path: str, name: str, start_line: int) -> str:
    """Generate unique chunk ID: file_path::name::Lstart_line"""
    return f"{file_path}::{name}::L{start_line}"


def count_tokens(text: str) -> int:
    """
    Count tokens accurately using tiktoken.

    Args:
        text: Code text to count

    Returns:
        Token count (accurate) or character-based estimate (fallback)
    """
    if TOKEN_ENCODER:
        try:
            return len(TOKEN_ENCODER.encode(text))
        except Exception:
            pass

    # Fallback: character-based estimation
    # Empirical ratio for code: ~4 chars per token
    return len(text) // 4


def extract_lines_from_content(file_content: str, start_line: int, end_line: int) -> str:
    """
    Extract specific lines from file content using line numbers.

    Args:
        file_content: Full file content
        start_line: Start line (1-indexed)
        end_line: End line (1-indexed, inclusive)

    Returns:
        Extracted code
    """
    lines = file_content.split('\n')
    # Convert to 0-indexed for array access
    start_idx = start_line - 1
    end_idx = end_line  # end_line is inclusive, so don't subtract 1

    if start_idx < 0 or end_idx > len(lines):
        return ""

    extracted = '\n'.join(lines[start_idx:end_idx])
    return extracted


def truncate_chunk_intelligently(code: str, max_tokens: int = 1000) -> tuple:
    """
    Truncate large code chunks intelligently while preserving structure.

    Strategy:
    - Keep: Full signature, docstring, first 20 lines of body
    - Add: "... (truncated, see full code)"
    - Ensures: Result is <max_tokens

    Args:
        code: Code to potentially truncate
        max_tokens: Maximum tokens allowed

    Returns:
        (truncated_code, was_truncated)
    """
    current_tokens = count_tokens(code)

    if current_tokens <= max_tokens:
        return code, False

    # Truncate: Keep signature + docstring + first 20 lines of body
    lines = code.split('\n')

    # Find signature (first non-empty line)
    signature_end = 0
    for i, line in enumerate(lines):
        if line.strip() and not line.strip().startswith('#'):
            signature_end = i
            break

    # Find docstring end (if exists)
    docstring_end = signature_end
    in_docstring = False
    docstring_quote = None

    for i in range(signature_end, min(len(lines), signature_end + 30)):
        line = lines[i].strip()
        if line.startswith('"""') or line.startswith("'''"):
            if not in_docstring:
                in_docstring = True
                docstring_quote = line[:3]
                if line.count(docstring_quote) >= 2:
                    # Single-line docstring
                    docstring_end = i + 1
                    break
            else:
                # End of multi-line docstring
                docstring_end = i + 1
                break

    # Keep signature + docstring + 20 body lines
    keep_until = min(len(lines), docstring_end + 20)
    truncated_lines = lines[:keep_until]
    truncated_lines.append("")
    truncated_lines.append("    # ... (code truncated for embedding efficiency)")
    truncated_lines.append("    # Full code available at chunk location")

    truncated_code = '\n'.join(truncated_lines)

    # Verify we're now under limit
    final_tokens = count_tokens(truncated_code)
    if final_tokens > max_tokens:
        # Aggressive truncation: just signature + docstring
        truncated_code = '\n'.join(lines[:docstring_end])
        truncated_code += "\n\n    # ... (code truncated)\n"

    return truncated_code, True


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
    Convert file AST info into method-level chunks.

    NEW: Creates separate chunks for:
    - Each top-level function
    - Each class definition (signature + docstring only)
    - Each method within classes

    Args:
        file_path: relative path to file
        ast_info: output from ast_parser (structured with line numbers)

    Returns:
        List of chunk dictionaries
    """
    chunks = []
    file_content = ast_info.get('content', '')

    if not file_content:
        return chunks

    # Check if we have NEW structured data (dicts) or OLD flat data (strings)
    functions = ast_info.get('functions', [])
    classes = ast_info.get('classes', [])

    is_structured = (functions and isinstance(functions[0], dict)) or (classes and isinstance(classes[0], dict))

    if not is_structured:
        # OLD FORMAT: Fallback to legacy chunking for backward compatibility
        logging.warning(f"Using legacy chunking for {file_path} (old AST format)")
        return chunk_file_legacy(file_path, ast_info)

    # NEW FORMAT: Method-level chunking

    # Extract top-level function chunks
    for func_info in functions:
        if isinstance(func_info, dict):
            func_name = func_info['name']
            start_line = func_info['lineno']
            end_line = func_info.get('end_lineno', start_line)

            code = extract_lines_from_content(file_content, start_line, end_line)

            if code:
                # Apply truncation if needed
                code, was_truncated = truncate_chunk_intelligently(code, max_tokens=1000)
                token_count = count_tokens(code)

                chunk_id = generate_chunk_id(file_path, func_name, start_line)
                chunks.append({
                    'chunk_id': chunk_id,
                    'file_path': file_path,
                    'type': 'function',
                    'name': func_name,
                    'code': code,
                    'start_line': start_line,
                    'end_line': end_line,
                    'tokens': token_count,
                    'metadata': {
                        'imports': ast_info.get('imports', []),
                        'file_type': file_path.split('.')[-1] if '.' in file_path else 'unknown',
                        'is_async': func_info.get('is_async', False),
                        'decorators': func_info.get('decorators', []),
                        'was_truncated': was_truncated
                    }
                })

    # Extract class chunks (definition + methods separately)
    for class_info in classes:
        if isinstance(class_info, dict):
            class_name = class_info['name']
            class_start = class_info['lineno']
            class_end = class_info.get('end_lineno', class_start)
            methods = class_info.get('methods', [])

            # Chunk 1: Class definition (signature + docstring only)
            if methods:
                # Extract until first method starts
                first_method_line = methods[0]['lineno']
                class_def_code = extract_lines_from_content(file_content, class_start, first_method_line - 1)
            else:
                # No methods, extract entire class (probably empty or just attributes)
                class_def_code = extract_lines_from_content(file_content, class_start, class_end)

            if class_def_code.strip():
                token_count = count_tokens(class_def_code)
                chunk_id = generate_chunk_id(file_path, class_name, class_start)
                chunks.append({
                    'chunk_id': chunk_id,
                    'file_path': file_path,
                    'type': 'class_definition',
                    'name': class_name,
                    'code': class_def_code,
                    'start_line': class_start,
                    'end_line': first_method_line - 1 if methods else class_end,
                    'tokens': token_count,
                    'metadata': {
                        'imports': ast_info.get('imports', []),
                        'file_type': file_path.split('.')[-1] if '.' in file_path else 'unknown',
                        'bases': class_info.get('bases', []),
                        'decorators': class_info.get('decorators', []),
                        'method_count': len(methods)
                    }
                })

            # Chunks 2-N: Each method separately
            for method_info in methods:
                method_name = method_info['name']
                method_start = method_info['lineno']
                method_end = method_info.get('end_lineno', method_start)

                method_code = extract_lines_from_content(file_content, method_start, method_end)

                if method_code:
                    # Apply truncation if needed
                    method_code, was_truncated = truncate_chunk_intelligently(method_code, max_tokens=1000)
                    token_count = count_tokens(method_code)

                    chunk_id = generate_chunk_id(file_path, f"{class_name}.{method_name}", method_start)
                    chunks.append({
                        'chunk_id': chunk_id,
                        'file_path': file_path,
                        'type': 'method',
                        'name': f"{class_name}.{method_name}",
                        'code': method_code,
                        'start_line': method_start,
                        'end_line': method_end,
                        'tokens': token_count,
                        'metadata': {
                            'imports': ast_info.get('imports', []),
                            'file_type': file_path.split('.')[-1] if '.' in file_path else 'unknown',
                            'parent_class': class_name,
                            'is_async': method_info.get('is_async', False),
                            'decorators': method_info.get('decorators', []),
                            'was_truncated': was_truncated
                        }
                    })

    # Extract module-level variables
    module_vars = extract_module_variables(file_path, file_content, ast_info)
    if ast_info.get('functions') or ast_info.get('classes'):
        chunks.extend(module_vars)

    # If no chunks created, create file-level chunk
    if not chunks and file_content:
        code, was_truncated = truncate_chunk_intelligently(file_content, max_tokens=2000)
        token_count = count_tokens(code)

        chunk_id = generate_chunk_id(file_path, 'file_content', 1)
        chunks.append({
            'chunk_id': chunk_id,
            'file_path': file_path,
            'type': 'file',
            'name': file_path.split('/')[-1],
            'code': code,
            'start_line': 1,
            'end_line': len(file_content.split('\n')),
            'tokens': token_count,
            'metadata': {
                'imports': ast_info.get('imports', []),
                'file_type': file_path.split('.')[-1] if '.' in file_path else 'unknown',
                'was_truncated': was_truncated
            }
        })

    # Log chunk statistics
    if chunks:
        avg_tokens = sum(c.get('tokens', 0) for c in chunks) / len(chunks)
        max_tokens = max(c.get('tokens', 0) for c in chunks)
        logging.debug(f"📊 {file_path}: {len(chunks)} chunks (avg: {avg_tokens:.0f} tokens, max: {max_tokens} tokens)")

    return chunks


def chunk_file_legacy(file_path: str, ast_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Legacy chunking for OLD AST format (backward compatibility).

    This is the old implementation that creates class-level chunks.
    Used when AST data doesn't have structured method information.
    """
    chunks = []
    file_content = ast_info.get('content', '')

    if not file_content:
        return chunks

    # Extract function chunks (old way)
    for func_name in ast_info.get('functions', []):
        if isinstance(func_name, str):
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

    # Extract class chunks (old way - entire class)
    for class_name in ast_info.get('classes', []):
        if isinstance(class_name, str):
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
    """
    Get comprehensive statistics about chunks for debugging/validation.

    NEW: Includes token statistics for embedding safety verification.
    """
    if not chunks:
        return {'total': 0}

    stats = {
        'total': len(chunks),
        'by_type': {},
        'avg_lines': 0,
        'avg_chars': 0,
        'avg_tokens': 0,
        'max_tokens': 0,
        'chunks_over_800_tokens': 0,
        'chunks_truncated': 0,
        'files_processed': len(set(c['file_path'] for c in chunks))
    }

    total_lines = 0
    total_chars = 0
    total_tokens = 0

    for chunk in chunks:
        chunk_type = chunk['type']
        stats['by_type'][chunk_type] = stats['by_type'].get(chunk_type, 0) + 1

        lines = chunk['end_line'] - chunk['start_line'] + 1
        total_lines += lines
        total_chars += len(chunk['code'])

        # Token statistics
        tokens = chunk.get('tokens', count_tokens(chunk['code']))
        total_tokens += tokens

        if tokens > stats['max_tokens']:
            stats['max_tokens'] = tokens

        if tokens > 800:
            stats['chunks_over_800_tokens'] += 1

        if chunk.get('metadata', {}).get('was_truncated'):
            stats['chunks_truncated'] += 1

    stats['avg_lines'] = total_lines / len(chunks)
    stats['avg_chars'] = total_chars / len(chunks)
    stats['avg_tokens'] = total_tokens / len(chunks)

    return stats
