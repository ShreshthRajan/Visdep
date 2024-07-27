import requests
import json

# Define the base URL for the API
BASE_URL = "http://127.0.0.1:8000/api"

# Function to upload the repository
def upload_repo(repo_url):
    response = requests.post(f"{BASE_URL}/upload_repo", json={"repo_url": repo_url})
    return response.json()

# Function to query the Jamba model
def query_jamba(query, context):
    response = requests.post(f"{BASE_URL}/query", json={"query": query, "context": json.dumps(context)})
    return response.json()

def test_jamba_integration():
    # Test repository upload
    repo_url = "https://github.com/ShreshthRajan/tensorflow"
    print("Uploading repository...")
    upload_response = upload_repo(repo_url)
    print(upload_response)

    # Define test questions and their respective contexts
    test_cases = [
        {
            "question": "What is the overall architecture of TensorFlow?",
            "context": {
                "TensorFlow": {
                    "README.md": {"functions": [], "classes": [], "imports": []},
                    # Add more relevant files and their parsed data
                }
            }
        },
        {
            "question": "How does TensorFlow implement distributed training?",
            "context": {
                "TensorFlow": {
                    "tensorflow/python/distribute/distribute_lib.py": {"functions": [], "classes": [], "imports": []},
                    # Add more relevant files and their parsed data
                }
            }
        },
        {
            "question": "How is the tf.GradientTape class implemented, and what are its use cases?",
            "context": {
                "TensorFlow": {
                    "tensorflow/python/eager/backprop.py": {"functions": ["GradientTape"], "classes": [], "imports": []},
                    # Add more relevant files and their parsed data
                }
            }
        },
        {
            "question": "What techniques does TensorFlow use to optimize computational performance?",
            "context": {
                "TensorFlow": {
                    "tensorflow/core/common_runtime/optimization_registry.h": {"functions": [], "classes": [], "imports": []},
                    # Add more relevant files and their parsed data
                }
            }
        }
    ]

    # Execute the test cases
    for case in test_cases:
        question = case["question"]
        context = case["context"]
        print(f"Querying: {question}")
        response = query_jamba(question, context)
        print(response)

if __name__ == "__main__":
    test_jamba_integration()
