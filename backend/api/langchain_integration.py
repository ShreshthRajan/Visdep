# dependency_extraction/backend/api/langchain_integration.py (new)
import os
from dotenv import load_dotenv
import logging
import requests
import json
import hashlib
import asyncio

# Adjust the import path for data_storage
from backend.api.data_storage import initialize_database, store_repository_metadata, store_ast_data
from backend.api.github_api import fetch_repo_content, fetch_repo_metadata
from backend.api.ast_parser import parse_code_to_ast
import hashlib

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
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationChain
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.runnable.history import RunnableWithMessageHistory
from langchain.schema.messages import HumanMessage, AIMessage
from langchain.memory.chat_message_histories import ChatMessageHistory


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

async def initialize_retrieval_qa(context):
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
    embeddings = AI21Embeddings(api_key=os.getenv("AI21_API_KEY"))
    vector_store = await FAISS.afrom_texts(documents, embeddings)

    # Create a ChatPromptTemplate with the correct input variable
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant."),
        ("human", "{context}")
    ])

    # Create an AI21LLM instance
    ai21_llm = AI21LLM(model="jamba-instruct-preview")

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

class ChatSession:
    def __init__(self):
        self.memory = ConversationBufferMemory(
            return_messages=True,
            memory_key="history",
            chat_memory=ChatMessageHistory()
        )
        self.conversation_chain = None

    async def initialize_conversation_chain(self, context):
        try:
            llm = AI21LLM(model="jamba-instruct-preview")
            
            few_shot_examples = """
            Example 1:
            Human: What are the main functions in the ast_parser.py file?
            AI: To answer this question, I'll analyze the ast_parser.py file in the context provided. Here's my step-by-step reasoning:

            1. First, I'll look for the 'ast_parser.py' entry in the context.
            2. I'll examine the 'functions' key in the file's information.
            3. I'll list out the main functions found.

            Based on the context provided, the main functions in ast_parser.py are:
            1. parse_python_file
            2. extract_python_info
            3. parse_javascript_file
            4. extract_javascript_info
            5. parse_java_file
            6. extract_java_info
            7. parse_go_file
            8. extract_go_info
            9. parse_cpp_file
            10. extract_cpp_info
            11. parse_html_file
            12. extract_html_info
            13. parse_sql_file
            14. extract_sql_info
            15. handle_non_code_file
            16. parse_code_file
            17. traverse_directory
            18. parse_code_to_ast
            19. download_repo_content

            These functions seem to be responsible for parsing different types of files and extracting relevant information from them.

            Example 2:
            Human: How does the chatbot handle user queries?
            AI: To answer this question, I'll analyze the relevant files in the context, particularly focusing on the chatbot implementation. Here's my step-by-step reasoning:

            1. I'll look for files related to the chatbot, such as 'chatbot.py' or similar.
            2. I'll examine the functions and classes defined in these files.
            3. I'll trace the flow of how a user query is processed.

            Based on the context provided, here's how the chatbot handles user queries:

            1. The chatbot uses a FastAPI endpoint '/chat' that accepts POST requests.
            2. The endpoint expects a QueryRequest object containing the user's query and context.
            3. It calls the `get_jamba_response` function from the langchain_integration module.
            4. The `get_jamba_response` function does the following:
            a. Initializes a retrieval QA system using the provided context.
            b. Constructs a series of messages including system instructions, context, and the user's query.
            c. Sends these messages to the AI21 Jamba model via an API call.
            d. Extracts the response from the model.
            5. The response is then returned to the user.
            6. If successful, it returns a QueryResponse object with the model's response.
            7. In case of errors, it raises an HTTPException with an appropriate error message.

            This process allows the chatbot to understand the context of the repository and provide relevant answers to user queries about the codebase.

            Human: Now, how can I assist you with your question about the repository?
            """

            prompt = ChatPromptTemplate.from_messages([
                ("system", f"You are an AI assistant specialized in analyzing GitHub repositories. Your responses should be clear, concise, and directly related to the repository content provided in the context. Here are some guidelines and examples of how to respond:\n\n{few_shot_examples}\n\nWhen answering, please follow these steps:\n1. Analyze the relevant parts of the repository context.\n2. If the information is not directly available, state that clearly.\n3. Provide a step-by-step explanation of your reasoning.\n4. Summarize your findings in a concise answer.\n5. If asked about previous responses, refer to your conversation history."),
                ("human", "{input}"),
            ])

            chain = RunnablePassthrough.assign(
                response=prompt | llm
            )

            self.conversation_chain = RunnableWithMessageHistory(
                chain,
                lambda session_id: self.memory,
                input_messages_key="input",
                history_messages_key="history",
            )
            logging.debug("Conversation chain initialized successfully")
        except Exception as e:
            logging.error(f"Error initializing conversation chain: {e}")
            raise

    async def chat(self, query, context):
        try:
            if not self.conversation_chain:
                await self.initialize_conversation_chain(context)

            session_id = hashlib.md5(json.dumps(context, sort_keys=True).encode()).hexdigest()
            response = await self.conversation_chain.ainvoke(
                {
                    "input": f"Repository context:\n{json.dumps(context, indent=2)}\n\nUser question: {query}",
                },
                config={"configurable": {"session_id": session_id}}
            )
            logging.debug(f"Chat response: {response}")
            return response['response']
        except Exception as e:
            logging.error(f"Error in ChatSession.chat: {e}")
            raise

chat_sessions = {}

async def get_jamba_response(query, context):
    try:
        logging.debug(f"Processing query: {query}")
        logging.debug(f"Context: {json.dumps(context, indent=2)}")

        # Initialize retrieval QA (now awaited)
        try:
            retrieval_qa = await initialize_retrieval_qa(context)
            logging.debug("Retrieval QA initialized successfully")
        except Exception as e:
            logging.error(f"Error initializing retrieval QA: {e}")
            raise

        # Construct messages for AI21 model
        messages = [
            {"role": "system", "content": "You are a helpful assistant specialized in analyzing GitHub repositories."},
            {"role": "user", "content": f"Repository context: {json.dumps(context, indent=2)}"},
            {"role": "user", "content": query}
        ]

        # Make API call to AI21 Jamba model
        try:
            endpoint_url = "https://api.ai21.com/studio/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {os.getenv('AI21_API_KEY')}",
                "Content-Type": "application/json"
            }
            input_data = {
                "model": "jamba-instruct-preview",
                "messages": messages
            }
            response = await asyncio.to_thread(requests.post, endpoint_url, headers=headers, json=input_data)
            logging.debug(f"Response from AI21 model: {response.json()}")
        except Exception as e:
            logging.error(f"Error making API call to AI21 model: {e}")
            raise

        if response.status_code == 200 and 'choices' in response.json() and len(response.json()['choices']) > 0:
            ai21_response = response.json()['choices'][0]['message']['content']

            # Use ChatSession for improved conversation
            try:
                context_string = json.dumps(context, sort_keys=True)
                session_id = hashlib.md5(context_string.encode()).hexdigest()

                if session_id not in chat_sessions:
                    chat_sessions[session_id] = ChatSession()

                chat_session = chat_sessions[session_id]
                improved_response = await chat_session.chat(query, context)
                logging.debug(f"Improved response: {improved_response}")
            except Exception as e:
                logging.error(f"Error in ChatSession processing: {e}")
                raise

            # Combine the responses without prefixes
            final_response = f"{ai21_response}\n\n{improved_response}"
            return final_response
        else:
            error_msg = f"No valid response received from the model. Status code: {response.status_code}, Response: {response.text}"
            logging.error(error_msg)
            raise ValueError(error_msg)
    except Exception as e:
        logging.error(f"Error in get_jamba_response: {e}")
        raise