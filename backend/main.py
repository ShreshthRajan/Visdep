import os
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from backend.api.github_api import fetch_repo_content, fetch_repo_metadata
from backend.api.langchain_integration import get_jamba_response
from backend.api.ast_parser import parse_code_to_ast
from backend.api.chatbot import router as chatbot_router  # Import the chatbot router
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

# Ensure AI21 API key and GitHub token are set
if not os.getenv("AI21_API_KEY"):
    raise RuntimeError("AI21_API_KEY environment variable is not set")
if not os.getenv("GITHUB_AUTH_TOKEN"):
    raise RuntimeError("GITHUB_AUTH_TOKEN environment variable is not set")

class RepoLink(BaseModel):
    repo_url: str

class QueryRequest(BaseModel):
    query: str
    context: str

def store_repo_data(repo_metadata):
    # Log the storage action for debugging
    print(f"Storing repository metadata: {repo_metadata}")

def store_parsed_data(parsed_data):
    # Log the storage action for debugging
    print(f"Storing parsed AST data: {parsed_data}")

@app.post("/api/upload_repo")
async def upload_repo(link: RepoLink):
    try:
        repo_url = link.repo_url
        auth_token = os.getenv("GITHUB_AUTH_TOKEN")
        
        # Fetch repository content and metadata
        repo_content = fetch_repo_content(repo_url, auth_token)
        repo_metadata = fetch_repo_metadata(repo_url, auth_token)
        
        # Parse the repository content to AST
        parsed_data = parse_code_to_ast(repo_content)
        
        # Store repository metadata and parsed AST data
        store_repo_data(repo_metadata)
        store_parsed_data(parsed_data)
        
        return {"message": "Repository data successfully uploaded and parsed."}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.post("/api/query")
async def query_jamba(request: QueryRequest):
    try:
        query = request.query
        context = request.context
        
        # Convert context string to a dictionary safely
        context_dict = json.loads(context) if isinstance(context, str) else context
        
        # Get response from Jamba model
        response = get_jamba_response(query, context_dict)
        
        if response:
            return {"response": response}
        else:
            raise HTTPException(status_code=500, detail="Failed to get a response from the model.")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

# Include the chatbot router
app.include_router(chatbot_router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)