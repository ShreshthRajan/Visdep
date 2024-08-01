# dependency_extraction/backend/api/langchain_integration.py
import os
from dotenv import load_dotenv
import logging
import requests

# Adjust the import path for data_storage
from backend.api.data_storage import initialize_database, store_repository_metadata, store_ast_data
from backend.api.github_api import fetch_repo_content, fetch_repo_metadata
from backend.api.ast_parser import parse_code_to_ast

# Initialize the database
initialize_database()

# Setup logging
logging.basicConfig(level=logging.DEBUG)

# Ensure FAISS can be imported
try:
    import faiss
    logging.info("Faiss imported successfully in langchain_integration!")
except ImportError as e:
    logging.error(f"Error importing faiss in langchain_integration: {e}")
    raise ImportError(f"Faiss import failed: {e}. Ensure faiss-cpu or faiss-gpu is installed.")

from langchain_ai21 import AI21LLM, AI21Embeddings
from langchain.prompts import ChatPromptTemplate
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain.schema import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableSequence
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain

# Load environment variables from .env file
load_dotenv()

# Ensure AI21 API key is set
if not os.getenv("AI21_API_KEY"):
    raise RuntimeError("AI21_API_KEY environment variable is not set")

def fetch_parse_store_repo(repo_url, auth_token):
    try:
        # Fetch repository content and metadata
        repo_content = fetch_repo_content(repo_url, auth_token)
        repo_metadata = fetch_repo_metadata(repo_url, auth_token)

        # Store repository metadata
        repo_name = repo_metadata.get('full_name')
        repo_id = store_repository_metadata(repo_name, repo_metadata)

        # Parse repository content to AST
        ast_data = parse_code_to_ast(repo_content)

        # Store parsed AST data
        for file_path, ast_info in ast_data.items():
            store_ast_data(repo_id, file_path, ast_info)

        return repo_id, ast_data

    except Exception as e:
        logging.error(f"Error in fetch_parse_store_repo: {e}")
        raise

def initialize_retrieval_qa(context):
    # Prepare documents from context
    documents = []
    for file_path, info in context.items():
        doc_content = f"File: {file_path}\n"
        if 'functions' in info:
            doc_content += f"Functions: {', '.join(info['functions'])}\n"
        if 'classes' in info:
            doc_content += f"Classes: {', '.join(info['classes'])}\n"
        if 'imports' in info:
            doc_content += f"Imports: {', '.join(info['imports'])}\n"
        documents.append(doc_content)

    logging.debug(f"Documents for vector store: {documents}")

    # Ensure there are documents to create the vector store
    if not documents:
        raise ValueError("No documents available to create the vector store.")

    # Initialize the vector store (FAISS) and embeddings (AI21)
    embeddings = AI21Embeddings(api_key=os.getenv("AI21_API_KEY"))  # AI21 embeddings
    vector_store = FAISS.from_texts(documents, embeddings)

    # Create a ChatPromptTemplate with the correct input variable
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant."),
        ("human", "{context}")
    ])

    # Create an AI21LLM instance
    ai21_llm = AI21LLM(model="jamba-instruct-preview")  # Provide the correct model name

    # Create a StuffDocumentsChain (combine_docs_chain)
    combine_docs_chain = create_stuff_documents_chain(
        llm=ai21_llm,
        prompt=prompt_template,
        document_variable_name="context"
    )

    # Create the retrieval chain with the correct parameters
    retrieval_qa = create_retrieval_chain(
        retriever=vector_store.as_retriever(),
        combine_docs_chain=combine_docs_chain
    )
    
    return retrieval_qa


def get_jamba_response(query, context):
    try:
        logging.debug(f"Initializing RetrievalQA with context: {context}")
        retrieval_qa = initialize_retrieval_qa(context)
        logging.info(f"Invoking with query: {query} and context: {context}")

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"Context: {context}"},
            {"role": "user", "content": query}
        ]

        logging.debug(f"Constructed messages for AI21 model: {messages}")

        input_data = {
            "model": "jamba-instruct-preview",
            "messages": messages
        }

        logging.debug(f"Input data for AI21 model: {input_data}")

        endpoint_url = "https://api.ai21.com/studio/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {os.getenv('AI21_API_KEY')}",
            "Content-Type": "application/json"
        }
        response = requests.post(endpoint_url, headers=headers, json=input_data)
        logging.debug(f"Response from AI21 model: {response.json()}")

        if response.status_code == 200 and 'choices' in response.json() and len(response.json()['choices']) > 0:
            return response.json()['choices'][0]['message']['content']
        else:
            logging.error(f"No valid response received from the model. Status code: {response.status_code}, Response: {response.text}")
            raise ValueError(f"No valid response received from the model. Status code: {response.status_code}, Response: {response.text}")
    except Exception as e:
        logging.error(f"Error in get_jamba_response: {e}")
        raise
