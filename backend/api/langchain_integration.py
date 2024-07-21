import os
from dotenv import load_dotenv

# Ensure FAISS can be imported
try:
    import faiss
    print("Faiss imported successfully in langchain_integration!")
except ImportError as e:
    print(f"Error importing faiss in langchain_integration: {e}")
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

    # Initialize the vector store (FAISS) and embeddings (AI21)
    embeddings = AI21Embeddings(api_key=os.getenv("AI21_API_KEY"))  # AI21 embeddings
    vector_store = FAISS.from_texts(documents, embeddings)

    # Create a ChatPromptTemplate with the correct input variable
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant."),
        ("human", "{context}")
    ])

    # Create an AI21LLM instance
    ai21_llm = AI21LLM(model="j2-jumbo-instruct")  # Provide the correct model name

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
    # Initialize the RetrievalQA chain with context
    retrieval_qa = initialize_retrieval_qa(context)
    response = retrieval_qa.invoke({"question": query, "context": context})
    return response['result']
