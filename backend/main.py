import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.api.github_api import fetch_repo_content, fetch_repo_metadata
from backend.api.langchain_integration import get_jamba_response
from backend.api.ast_parser import parse_code_to_ast
from backend.api.data_storage import store_repository_metadata, store_ast_data
from backend.api.chatbot import router as chatbot_router
from backend.api.graph_generator import create_dependency_graph, save_graph_as_json, load_graph_from_json
from networkx.readwrite import json_graph
from dotenv import load_dotenv
import logging

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

# Add CORS middleware to allow requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to your frontend's origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        logging.debug(f"Fetching content for repo: {repo_url}")
        repo_content = fetch_repo_content(repo_url, auth_token)
        logging.debug(f"Fetched repo content: {repo_content}")
        
        repo_metadata = fetch_repo_metadata(repo_url, auth_token)
        logging.debug(f"Fetched repo metadata: {repo_metadata}")
        
        # Parse the repository content to AST
        parsed_data = parse_code_to_ast(repo_content)
        logging.debug(f"Parsed AST data: {parsed_data}")
        
        # Store repository metadata and parsed AST data
        repo_id = store_repository_metadata(repo_metadata['full_name'], repo_metadata)
        for file_path, ast_info in parsed_data.items():
            store_ast_data(repo_id, file_path, ast_info)

        # Save parsed data as context
        with open("context.json", "w") as context_file:
            json.dump(parsed_data, context_file)
        
        # Create and save the dependency graph
        graph = create_dependency_graph(parsed_data)
        save_graph_as_json(graph, "dependency_graph.json")
        
        return {"message": "Repository data successfully uploaded, parsed, and graph generated."}
    
    except Exception as e:
        logging.error(f"Error in upload_repo: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")



@app.get("/api/dependency_graph")
async def get_dependency_graph():
    try:
        graph = load_graph_from_json("dependency_graph.json")
        data = json_graph.node_link_data(graph)
        return {"nodes": data["nodes"], "edges": data["links"]}
    except Exception as e:
        logging.error(f"Error in get_dependency_graph: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.post("/api/query")
async def query_jamba(request: QueryRequest):
    try:
        query = request.query
        repo_name = request.context  # Use repo_name as context
        
        # Load the context from the file
        with open("context.json", "r") as context_file:
            context_dict = json.load(context_file)
        
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

@app.get("/api/context")
async def get_context():
    try:
        with open("context.json", "r") as context_file:
            context = json.load(context_file)
        return context
    except Exception as e:
        logging.error(f"Error in get_context: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
