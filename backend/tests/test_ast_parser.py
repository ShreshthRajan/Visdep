import unittest
from backend.api.ast_parser import (
    parse_code_file, extract_python_info, parse_python_file,
    TREE_SITTER_AVAILABLE
)
import os
import tempfile

class TestASTParser(unittest.TestCase):

    def test_parse_python_file(self):
        sample_code = """
def hello_world():
    print("Hello, world!")
"""
        with open('test_file.py', 'w') as f:
            f.write(sample_code)

        tree = parse_python_file('test_file.py')  # Directly using parse_python_file for AST
        info = extract_python_info(tree)

        self.assertIn('hello_world', info['functions'])
        os.remove('test_file.py')

    # Add more tests for other languages and file types


class TestPHPParser(unittest.TestCase):
    """Comprehensive PHP parsing tests"""

    @classmethod
    def setUpClass(cls):
        """Skip all PHP tests if tree-sitter not available"""
        if not TREE_SITTER_AVAILABLE:
            raise unittest.SkipTest("tree-sitter-language-pack not installed")

    def _create_php_file(self, content):
        """Helper to create temp PHP file"""
        fd, path = tempfile.mkstemp(suffix='.php')
        with os.fdopen(fd, 'w') as f:
            f.write(content)
        return path

    def test_php_function_parsing(self):
        """Test parsing top-level PHP functions"""
        php_code = '''<?php
function validateInput(array $data): bool {
    return !empty($data);
}

function processData($input) {
    return $input;
}
'''
        path = self._create_php_file(php_code)
        try:
            info = parse_code_file(path)

            self.assertEqual(len(info['functions']), 2)

            func_names = [f['name'] for f in info['functions']]
            self.assertIn('validateInput', func_names)
            self.assertIn('processData', func_names)

            # Verify structured format
            validate_func = next(f for f in info['functions'] if f['name'] == 'validateInput')
            self.assertIn('lineno', validate_func)
            self.assertIn('end_lineno', validate_func)
            self.assertIn('decorators', validate_func)
            self.assertGreater(validate_func['end_lineno'], validate_func['lineno'])
        finally:
            os.remove(path)

    def test_php_class_with_methods(self):
        """Test parsing PHP class with methods"""
        php_code = '''<?php
class UserController extends BaseController {
    public function __construct() {
        parent::__construct();
    }

    public function index(): Response {
        return view("users.index");
    }

    public static function create(Request $request): User {
        return User::create($request->all());
    }

    private function helper(): void {
        // private method
    }
}
'''
        path = self._create_php_file(php_code)
        try:
            info = parse_code_file(path)

            self.assertEqual(len(info['classes']), 1)
            cls = info['classes'][0]

            self.assertEqual(cls['name'], 'UserController')
            self.assertEqual(len(cls['methods']), 4)

            method_names = [m['name'] for m in cls['methods']]
            self.assertIn('__construct', method_names)
            self.assertIn('index', method_names)
            self.assertIn('create', method_names)
            self.assertIn('helper', method_names)

            # Verify method structure
            index_method = next(m for m in cls['methods'] if m['name'] == 'index')
            self.assertIn('lineno', index_method)
            self.assertIn('end_lineno', index_method)

            # Verify base class extraction
            self.assertIn('BaseController', cls['bases'])
        finally:
            os.remove(path)

    def test_php_trait_parsing(self):
        """Test parsing PHP traits"""
        php_code = '''<?php
trait Loggable {
    public function log(string $message): void {
        echo $message;
    }

    protected function debug($data): void {
        var_dump($data);
    }
}
'''
        path = self._create_php_file(php_code)
        try:
            info = parse_code_file(path)

            self.assertEqual(len(info['classes']), 1)
            trait = info['classes'][0]

            self.assertEqual(trait['name'], 'Loggable')
            self.assertEqual(len(trait['methods']), 2)

            method_names = [m['name'] for m in trait['methods']]
            self.assertIn('log', method_names)
            self.assertIn('debug', method_names)
        finally:
            os.remove(path)

    def test_php_interface_parsing(self):
        """Test parsing PHP interfaces"""
        php_code = '''<?php
interface Repository {
    public function find(int $id): ?Model;
    public function save(Model $model): bool;
    public function delete(int $id): void;
}
'''
        path = self._create_php_file(php_code)
        try:
            info = parse_code_file(path)

            self.assertEqual(len(info['classes']), 1)
            interface = info['classes'][0]

            self.assertEqual(interface['name'], 'Repository')
            self.assertEqual(len(interface['methods']), 3)
        finally:
            os.remove(path)

    def test_php_enum_parsing(self):
        """Test parsing PHP 8.1+ enums"""
        php_code = '''<?php
enum Status: string {
    case Active = "active";
    case Inactive = "inactive";

    public function label(): string {
        return ucfirst($this->value);
    }
}
'''
        path = self._create_php_file(php_code)
        try:
            info = parse_code_file(path)

            self.assertEqual(len(info['classes']), 1)
            enum = info['classes'][0]

            self.assertEqual(enum['name'], 'Status')
            self.assertEqual(len(enum['methods']), 1)
            self.assertEqual(enum['methods'][0]['name'], 'label')
        finally:
            os.remove(path)

    def test_php_single_import(self):
        """Test parsing single use statements"""
        php_code = '''<?php
use App\\Models\\User;
use Illuminate\\Http\\Request;

class Controller {}
'''
        path = self._create_php_file(php_code)
        try:
            info = parse_code_file(path)

            self.assertEqual(len(info['imports']), 2)
            self.assertIn('App\\Models\\User', info['imports'])
            self.assertIn('Illuminate\\Http\\Request', info['imports'])
        finally:
            os.remove(path)

    def test_php_grouped_imports(self):
        """Test parsing grouped use statements"""
        php_code = '''<?php
use App\\Models\\{User, Post, Comment};

class Controller {}
'''
        path = self._create_php_file(php_code)
        try:
            info = parse_code_file(path)

            self.assertEqual(len(info['imports']), 3)
            self.assertIn('App\\Models\\User', info['imports'])
            self.assertIn('App\\Models\\Post', info['imports'])
            self.assertIn('App\\Models\\Comment', info['imports'])
        finally:
            os.remove(path)

    def test_php8_attributes(self):
        """Test parsing PHP 8 attributes as decorators"""
        php_code = '''<?php
#[Route("/api/users")]
#[Middleware("auth")]
class ApiController {
    #[Get("/")]
    #[Cache(ttl: 3600)]
    public function index(): array {
        return [];
    }
}
'''
        path = self._create_php_file(php_code)
        try:
            info = parse_code_file(path)

            self.assertEqual(len(info['classes']), 1)
            cls = info['classes'][0]

            # Class attributes
            self.assertEqual(len(cls['decorators']), 2)
            self.assertTrue(any('Route' in d for d in cls['decorators']))
            self.assertTrue(any('Middleware' in d for d in cls['decorators']))

            # Method attributes
            method = cls['methods'][0]
            self.assertEqual(len(method['decorators']), 2)
            self.assertTrue(any('Get' in d for d in method['decorators']))
            self.assertTrue(any('Cache' in d for d in method['decorators']))
        finally:
            os.remove(path)

    def test_php_class_implements(self):
        """Test parsing class implements clause"""
        php_code = '''<?php
class User extends Model implements Authenticatable, HasRoles {
    public function getAuthIdentifier(): int {
        return $this->id;
    }
}
'''
        path = self._create_php_file(php_code)
        try:
            info = parse_code_file(path)

            cls = info['classes'][0]

            # Should include both extends and implements in bases
            self.assertIn('Model', cls['bases'])
            self.assertIn('Authenticatable', cls['bases'])
            self.assertIn('HasRoles', cls['bases'])
        finally:
            os.remove(path)

    def test_php_abstract_class(self):
        """Test parsing abstract class with abstract methods"""
        php_code = '''<?php
abstract class BaseService {
    abstract protected function process(): array;

    public function run(): void {
        $this->process();
    }
}
'''
        path = self._create_php_file(php_code)
        try:
            info = parse_code_file(path)

            cls = info['classes'][0]
            self.assertEqual(cls['name'], 'BaseService')
            self.assertEqual(len(cls['methods']), 2)
        finally:
            os.remove(path)

    def test_php_has_content(self):
        """Test that content is included in output"""
        php_code = '''<?php
function test() {}
'''
        path = self._create_php_file(php_code)
        try:
            info = parse_code_file(path)

            self.assertIn('content', info)
            self.assertIn('<?php', info['content'])
            self.assertIn('function test', info['content'])
        finally:
            os.remove(path)

    def test_php_complex_file(self):
        """Integration test with complex PHP file (like OpenVK)"""
        php_code = '''<?php
namespace App\\Controllers;

use App\\Models\\User;
use App\\Services\\{AuthService, LogService};
use Illuminate\\Http\\Request;

function validateInput(array $data): bool {
    return !empty($data);
}

#[Route("/users")]
class UserController extends BaseController implements Loggable {
    public function __construct(
        private UserService $service
    ) {}

    #[Get("/")]
    public function index(): Response {
        return view("users.index");
    }

    public static function create(Request $request): User {
        return User::create($request->all());
    }
}

trait Auditable {
    public function audit(): void {
        echo "Auditing...";
    }
}

interface Repository {
    public function find(int $id): ?Model;
}

enum Status: string {
    case Active = "active";

    public function label(): string {
        return ucfirst($this->value);
    }
}
'''
        path = self._create_php_file(php_code)
        try:
            info = parse_code_file(path)

            # Verify functions
            self.assertEqual(len(info['functions']), 1)
            self.assertEqual(info['functions'][0]['name'], 'validateInput')

            # Verify classes (class, trait, interface, enum)
            self.assertEqual(len(info['classes']), 4)
            class_names = [c['name'] for c in info['classes']]
            self.assertIn('UserController', class_names)
            self.assertIn('Auditable', class_names)
            self.assertIn('Repository', class_names)
            self.assertIn('Status', class_names)

            # Verify imports
            self.assertEqual(len(info['imports']), 4)
            self.assertIn('App\\Models\\User', info['imports'])
            self.assertIn('App\\Services\\AuthService', info['imports'])
            self.assertIn('App\\Services\\LogService', info['imports'])
            self.assertIn('Illuminate\\Http\\Request', info['imports'])

            # Verify UserController details
            user_ctrl = next(c for c in info['classes'] if c['name'] == 'UserController')
            self.assertEqual(len(user_ctrl['methods']), 3)
            self.assertIn('BaseController', user_ctrl['bases'])
            self.assertIn('Loggable', user_ctrl['bases'])
            self.assertTrue(any('Route' in d for d in user_ctrl['decorators']))

            # Verify content preserved
            self.assertIn('content', info)
        finally:
            os.remove(path)


if __name__ == '__main__':
    unittest.main()
