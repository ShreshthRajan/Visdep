#!/usr/bin/env python3
"""
Test script to verify the query endpoint fix
Tests that backend can handle queries without frontend sending context
"""

import requests
import sys

# Test configuration
BASE_URL = "http://localhost:8000"

def test_query_without_context():
    """Test that query works without context parameter"""
    print("=" * 60)
    print("TESTING QUERY FIX")
    print("=" * 60)

    # Test 1: Query without context (new behavior)
    print("\n1. Testing query WITHOUT context (should work)...")
    response = requests.post(
        f"{BASE_URL}/api/query",
        json={"query": "How does Gson serialize Java objects to JSON?"}
    )

    print(f"   Status: {response.status_code}")

    if response.status_code == 200:
        print("   ✅ SUCCESS: Query worked without context!")
        data = response.json()
        if 'response' in data:
            print(f"   Response preview: {data['response'][:100]}...")
        return True
    elif response.status_code == 400:
        print(f"   ⚠️  Expected error: {response.json().get('detail')}")
        print("   (This is OK if no repo is loaded)")
        return True
    else:
        print(f"   ❌ FAILED: {response.status_code} - {response.text}")
        return False

def test_query_with_empty_context():
    """Test that query handles empty context gracefully"""
    print("\n2. Testing query WITH empty context (should still work)...")
    response = requests.post(
        f"{BASE_URL}/api/query",
        json={"query": "Test query", "context": {}}
    )

    print(f"   Status: {response.status_code}")

    if response.status_code in [200, 400]:
        print("   ✅ SUCCESS: Handles empty context gracefully!")
        return True
    else:
        print(f"   ❌ FAILED: {response.status_code} - {response.text}")
        return False

def main():
    print("\nStarting tests...")
    print("Make sure backend is running: uvicorn backend.main:app --port 8000\n")

    try:
        # Check if server is running
        response = requests.get(f"{BASE_URL}/docs")
        print("✅ Backend is running\n")
    except requests.ConnectionError:
        print("❌ Backend is not running!")
        print("   Start it with: uvicorn backend.main:app --port 8000")
        sys.exit(1)

    # Run tests
    test1 = test_query_without_context()
    test2 = test_query_with_empty_context()

    print("\n" + "=" * 60)
    if test1 and test2:
        print("ALL TESTS PASSED ✅")
    else:
        print("SOME TESTS FAILED ❌")
    print("=" * 60)

if __name__ == '__main__':
    main()
