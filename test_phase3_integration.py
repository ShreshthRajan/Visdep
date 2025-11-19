#!/usr/bin/env python3
"""
Phase 3 Integration Test
Tests C++ and Rust parsing with tree-sitter
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend', 'api'))

from ast_parser import parse_code_file
import tempfile

def test_cpp_parsing():
    """Test C++ parsing extracts functions and classes"""
    cpp_code = """
#include <iostream>

class Vector {
public:
    void add(int x) {
        data.push_back(x);
    }

    int get(int i) {
        return data[i];
    }
};

void printHello() {
    std::cout << "Hello" << std::endl;
}
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False) as f:
        f.write(cpp_code)
        f.flush()

        result = parse_code_file(f.name)

        os.unlink(f.name)

        print("C++ Parsing Results:")
        print(f"  Functions: {[f['name'] for f in result.get('functions', [])]}")
        print(f"  Classes: {[c['name'] for c in result.get('classes', [])]}")

        if result.get('classes'):
            cls = result['classes'][0]
            print(f"  Methods in {cls['name']}: {[m['name'] for m in cls.get('methods', [])]}")

        # Validate
        assert 'printHello' in [f['name'] for f in result.get('functions', [])]
        assert 'Vector' in [c['name'] for c in result.get('classes', [])]
        assert len(result['classes'][0]['methods']) == 2
        print("✅ C++ parsing PASSED\n")


def test_rust_parsing():
    """Test Rust parsing extracts functions and impl blocks"""
    rust_code = """
use std::collections::HashMap;

fn calculate(x: i32, y: i32) -> i32 {
    x + y
}

struct Person {
    name: String,
    age: u32,
}

impl Person {
    fn new(name: String, age: u32) -> Self {
        Person { name, age }
    }

    fn greet(&self) {
        println!("Hello, I'm {}", self.name);
    }
}
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
        f.write(rust_code)
        f.flush()

        result = parse_code_file(f.name)

        os.unlink(f.name)

        print("Rust Parsing Results:")
        print(f"  Functions: {[f['name'] for f in result.get('functions', [])]}")
        print(f"  Classes (impl blocks): {[c['name'] for c in result.get('classes', [])]}")

        if result.get('classes'):
            cls = result['classes'][0]
            print(f"  Methods in {cls['name']}: {[m['name'] for m in cls.get('methods', [])]}")

        # Validate
        assert 'calculate' in [f['name'] for f in result.get('functions', [])]
        assert 'Person' in [c['name'] for c in result.get('classes', [])]
        assert len(result['classes'][0]['methods']) == 2
        print("✅ Rust parsing PASSED\n")


if __name__ == '__main__':
    print("=" * 60)
    print("PHASE 3 INTEGRATION TEST")
    print("=" * 60)
    print()

    try:
        from tree_sitter_language_pack import get_parser
        print("✅ tree-sitter-language-pack installed\n")
    except ImportError:
        print("❌ tree-sitter-language-pack NOT installed")
        print("   Run: pip install tree-sitter-language-pack\n")
        sys.exit(1)

    test_cpp_parsing()
    test_rust_parsing()

    print("=" * 60)
    print("ALL TESTS PASSED ✅")
    print("=" * 60)
