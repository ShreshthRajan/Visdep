from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging
from backend.api.langchain_integration import get_jamba_response
import json

router = APIRouter()

# Setup logging
logging.basicConfig(level=logging.DEBUG)

# Define the request model
class QueryRequest(BaseModel):
    query: str
    context: str

# Define the response model
class QueryResponse(BaseModel):
    response: str

# Endpoint to handle user queries
@router.post("/chat", response_model=QueryResponse)
async def chat_with_jamba(request: QueryRequest):
    try:
        query = request.query
        context = request.context
        
        # Convert context string to a dictionary safely
        context_dict = json.loads(context) if isinstance(context, str) else context
        
        # Get response from Jamba model
        response = get_jamba_response(query, context_dict)
        
        if response:
            return QueryResponse(response=response)
        else:
            raise HTTPException(status_code=500, detail="Failed to get a response from the model.")
    
    except Exception as e:
        logging.error(f"Error in chat_with_jamba: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
