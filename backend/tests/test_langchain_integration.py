import requests
import os

def upload_repository(repo_url):
    response = requests.post(
        "http://127.0.0.1:8000/api/upload_repo",
        json={"repo_url": repo_url}
    )
    print("Uploading repository...")
    print(response.json())

def query_jamba(query, context):
    response = requests.post(
        "http://127.0.0.1:8000/api/query",
        json={"query": query, "context": context}
    )
    print(f"Querying: {query}")
    print(response.json())

if __name__ == "__main__":
    repo_url = "https://github.com/ShreshthRajan/gpt-engineer"
    upload_repository(repo_url)
    
    queries = [
        {
            "query": "What is gpt engineer?",
            "context": "{\"GPT_Engineer\": {\"README.md\": {\"functions\": [], \"classes\": [], \"imports\": []}}}"
        },
    ]
    
    for q in queries:
        query_jamba(q["query"], q["context"])
