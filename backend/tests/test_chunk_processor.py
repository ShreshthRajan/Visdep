# backend/tests/test_chunk_processor.py

import unittest
from backend.api.chunk_processor import (
    generate_chunk_id,
    extract_function_body,
    extract_class_body,
    chunk_file,
    process_repository_to_chunks,
    validate_chunk,
    get_chunk_stats
)


class TestChunkProcessor(unittest.TestCase):

    def test_generate_chunk_id(self):
        """Test chunk ID generation"""
        chunk_id = generate_chunk_id("auth/login.py", "verify_password", 42)
        self.assertEqual(chunk_id, "auth/login.py::verify_password::L42")

    def test_extract_function_body_python(self):
        """Test extracting Python function body"""
        code = """
def hello_world():
    print("Hello")
    return True

def another_function():
    pass
"""
        body, start, end = extract_function_body(code, "hello_world")
        self.assertIn("def hello_world()", body)
        self.assertIn('print("Hello")', body)
        self.assertNotIn("another_function", body)
        self.assertGreater(end, start)

    def test_extract_function_body_javascript(self):
        """Test extracting JavaScript function body"""
        code = """
function calculate(x, y) {
    const result = x + y;
    return result;
}

function other() {
    return 0;
}
"""
        body, start, end = extract_function_body(code, "calculate")
        self.assertIn("function calculate", body)
        self.assertIn("const result", body)
        self.assertNotIn("function other", body)

    def test_extract_class_body_python(self):
        """Test extracting Python class body"""
        code = """
class User:
    def __init__(self, name):
        self.name = name

    def greet(self):
        return f"Hello {self.name}"

class Admin:
    pass
"""
        body, start, end = extract_class_body(code, "User")
        self.assertIn("class User", body)
        self.assertIn("def __init__", body)
        self.assertIn("def greet", body)
        self.assertNotIn("class Admin", body)

    def test_chunk_file_with_functions(self):
        """Test chunking a file with functions"""
        file_content = """
def function_one():
    return 1

def function_two():
    return 2
"""
        ast_info = {
            'functions': ['function_one', 'function_two'],
            'classes': [],
            'imports': ['os', 'sys'],
            'content': file_content
        }

        chunks = chunk_file("test.py", ast_info)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]['type'], 'function')
        self.assertEqual(chunks[0]['name'], 'function_one')
        self.assertEqual(chunks[1]['name'], 'function_two')
        self.assertIn('imports', chunks[0]['metadata'])

    def test_chunk_file_with_classes(self):
        """Test chunking a file with classes"""
        file_content = """
class MyClass:
    def method(self):
        pass
"""
        ast_info = {
            'functions': [],
            'classes': ['MyClass'],
            'imports': [],
            'content': file_content
        }

        chunks = chunk_file("test.py", ast_info)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]['type'], 'class')
        self.assertEqual(chunks[0]['name'], 'MyClass')

    def test_chunk_file_empty_creates_file_chunk(self):
        """Test that files with no functions/classes get file-level chunk"""
        file_content = "# Configuration file\nCONFIG = {'key': 'value'}"

        ast_info = {
            'functions': [],
            'classes': [],
            'imports': [],
            'content': file_content
        }

        chunks = chunk_file("config.py", ast_info)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]['type'], 'file')

    def test_process_repository_to_chunks(self):
        """Test processing multiple files"""
        ast_data = {
            'file1.py': {
                'functions': ['func1'],
                'classes': [],
                'imports': [],
                'content': 'def func1():\n    pass'
            },
            'file2.py': {
                'functions': ['func2'],
                'classes': [],
                'imports': [],
                'content': 'def func2():\n    pass'
            }
        }

        chunks = process_repository_to_chunks(ast_data)

        self.assertEqual(len(chunks), 2)
        file_paths = {c['file_path'] for c in chunks}
        self.assertEqual(file_paths, {'file1.py', 'file2.py'})

    def test_validate_chunk_valid(self):
        """Test validation accepts valid chunk"""
        chunk = {
            'chunk_id': 'test.py::func::L1',
            'file_path': 'test.py',
            'type': 'function',
            'name': 'func',
            'code': 'def func():\n    return True',
            'start_line': 1,
            'end_line': 2,
            'metadata': {'imports': []}
        }

        self.assertTrue(validate_chunk(chunk))

    def test_validate_chunk_missing_field(self):
        """Test validation rejects chunk missing required field"""
        chunk = {
            'chunk_id': 'test.py::func::L1',
            'file_path': 'test.py',
            # Missing 'type'
            'name': 'func',
            'code': 'def func():\n    pass',
            'start_line': 1,
            'end_line': 2,
            'metadata': {}
        }

        self.assertFalse(validate_chunk(chunk))

    def test_validate_chunk_empty_code(self):
        """Test validation rejects empty code"""
        chunk = {
            'chunk_id': 'test.py::func::L1',
            'file_path': 'test.py',
            'type': 'function',
            'name': 'func',
            'code': '   ',  # Whitespace only
            'start_line': 1,
            'end_line': 2,
            'metadata': {}
        }

        self.assertFalse(validate_chunk(chunk))

    def test_validate_chunk_invalid_lines(self):
        """Test validation rejects invalid line numbers"""
        chunk = {
            'chunk_id': 'test.py::func::L1',
            'file_path': 'test.py',
            'type': 'function',
            'name': 'func',
            'code': 'def func(): pass',
            'start_line': 5,
            'end_line': 3,  # End before start
            'metadata': {}
        }

        self.assertFalse(validate_chunk(chunk))

    def test_get_chunk_stats(self):
        """Test statistics generation"""
        chunks = [
            {
                'chunk_id': '1',
                'file_path': 'file1.py',
                'type': 'function',
                'name': 'f1',
                'code': 'def f1():\n    pass',
                'start_line': 1,
                'end_line': 2,
                'metadata': {}
            },
            {
                'chunk_id': '2',
                'file_path': 'file1.py',
                'type': 'class',
                'name': 'C1',
                'code': 'class C1:\n    pass',
                'start_line': 4,
                'end_line': 5,
                'metadata': {}
            }
        ]

        stats = get_chunk_stats(chunks)

        self.assertEqual(stats['total'], 2)
        self.assertEqual(stats['by_type']['function'], 1)
        self.assertEqual(stats['by_type']['class'], 1)
        self.assertEqual(stats['files_processed'], 1)
        self.assertGreater(stats['avg_lines'], 0)
        self.assertGreater(stats['avg_chars'], 0)

    def test_get_chunk_stats_empty(self):
        """Test statistics with empty list"""
        stats = get_chunk_stats([])
        self.assertEqual(stats['total'], 0)


if __name__ == '__main__':
    unittest.main()
