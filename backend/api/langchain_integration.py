import os
from langchain.llms import OpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.document_loaders import TextLoader
from langchain.chains import RetrievalQA
from langchain.vectorstores import FAISS
from langchain.embeddings import OpenAIEmbeddings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Ensure AI21 API key is set
if not os.getenv("AI21_API_KEY"):
    raise RuntimeError("AI21_API_KEY environment variable is not set")

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

    # Initialize the vector store (FAISS) and embeddings (OpenAI)
    embeddings = OpenAIEmbeddings()
    vector_store = FAISS.from_texts(documents, embeddings)

    # Create the retrieval QA chain
    retrieval_qa = RetrievalQA(
        retriever=vector_store.as_retriever(),
        llm=OpenAI(api_key=os.getenv("AI21_API_KEY"))
    )
    
    return retrieval_qa

def get_jamba_response(query, context):
    # Initialize the RetrievalQA chain with context
    retrieval_qa = initialize_retrieval_qa(context)
    response = retrieval_qa({"query": query})
    return response['result']

# Test the integration
if __name__ == "__main__":
    query = "Where does data flow through the gateway?"
    context = {
        "example.py": {
            "functions": ["main", "gateway_function"],
            "classes": ["Gateway"],
            "imports": ["os", "sys"]
        }
    }
    response = get_jamba_response(query, context)
    if response:
        print(response)
    else:
        print("Failed to get a response from the model.")
