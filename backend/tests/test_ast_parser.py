import unittest
from api.ast_parser import parse_code_file, extract_python_info

class TestASTParser(unittest.TestCase):
    
    def test_parse_python_file(self):
        sample_code = """
        def hello_world():
            print("Hello, world!")
        """
        with open('test_file.py', 'w') as f:
            f.write(sample_code)
        
        tree = parse_code_file('test_file.py')
        info = extract_python_info(tree)
        
        self.assertIn('hello_world', info['functions'])
    
    # Add more tests for other languages and file types

if __name__ == '__main__':
    unittest.main()
