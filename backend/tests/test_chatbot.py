import json 
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

@pytest.fixture
def test_data():
    return {
        "query": "What are the functions in this repository?",
        "context": json.dumps({
            "file1.py": {
                "functions": ["function1", "function2"],
                "classes": ["Class1"],
                "imports": ["import1"]
            },
            "file2.py": {
                "functions": ["function3"],
                "classes": ["Class2"],
                "imports": ["import2"]
            }
        })
    }

def test_chat_with_jamba(test_data):
    response = client.post("/api/chat", json=test_data)
    assert response.status_code == 200
    assert "response" in response.json()

def test_invalid_context():
    invalid_data = {
        "query": "List all classes.",
        "context": "Invalid context"
    }
    response = client.post("/api/chat", json=invalid_data)
    assert response.status_code == 500
    assert "detail" in response.json()
