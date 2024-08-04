import os
from dotenv import load_dotenv
import logging
import requests
import json
import hashlib
import asyncio
from typing import List

# Adjust the import path for data_storage
from backend.api.data_storage import initialize_database, store_repository_metadata, store_ast_data
from backend.api.github_api import fetch_repo_content, fetch_repo_metadata
from backend.api.ast_parser import parse_code_to_ast
from langchain.prompts import MessagesPlaceholder


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
from langchain.memory.chat_message_histories import ChatMessageHistory
from langchain.schema import BaseMemory, BaseChatMessageHistory
from langchain.schema.messages import AIMessage, HumanMessage
from langchain.schema.messages import BaseMessage
from langchain.chains import LLMChain
from langchain.llms.base import LLM
from langchain.callbacks.manager import CallbackManagerForLLMRun
from typing import Any, List, Mapping, Optional

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

# class AsyncConversationBufferMemory(BaseMemory):
#     chat_memory: ChatMessageHistory = ChatMessageHistory()
#     return_messages: bool = True
#     memory_key: str = "history"

#     @property
#     def memory_variables(self) -> List[str]:
#         return [self.memory_key]

#     async def load_memory_variables(self, inputs: dict) -> dict:
#         return {self.memory_key: self.chat_memory.messages}

#     async def save_context(self, inputs: dict, outputs: dict) -> None:
#         self.chat_memory.add_user_message(inputs["input"])
#         self.chat_memory.add_ai_message(outputs["output"])

#     async def clear(self) -> None:
#         self.chat_memory.clear()

#     def get_messages(self) -> List[BaseMessage]:
#         return self.chat_memory.messages

class CustomAI21ChatLLM(LLM):
    model: str = "jamba-instruct-preview"
    api_key: str
    api_base: str = "https://api.ai21.com/studio/v1/chat/completions"

    def _call(self, prompt: str, stop: Optional[List[str]] = None, run_manager: Optional[CallbackManagerForLLMRun] = None, **kwargs: Any) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}]
        }
        response = requests.post(self.api_base, headers=headers, json=data)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    @property
    def _llm_type(self) -> str:
        return "custom_ai21_chat"

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {"model": self.model, "api_base": self.api_base}
    
chat_sessions = {} 

class ChatSession:
    def __init__(self):
        self.memory = ConversationBufferMemory(return_messages=True, memory_key="history")
        self.conversation_chain = None

    async def initialize_conversation_chain(self, context):
        try:
            logging.debug("Initializing CustomAI21ChatLLM")
            llm = CustomAI21ChatLLM(api_key=os.getenv("AI21_API_KEY"))
            logging.debug(f"CustomAI21ChatLLM initialized with model: {llm.model}")
            
            few_shot_examples = """
            Example 1:
            Human: What are the main functions in the ast_parser.py file?
            AI: To answer this question, I'll analyze the ast_parser.py file in the context provided. Here's my step-by-step reasoning:

            1. First, I'll look for the 'ast_parser.py' entry in the context.
            2. I'll examine the 'functions' key in the file's information.
            3. I'll list out the main functions found.

            Based on the context provided, the main functions in ast_parser.py are:
            [List of functions]

            These functions seem to be responsible for parsing different types of files and extracting relevant information from them.

            Example 2:
            Human: How does the chatbot handle user queries?
            AI: To answer this question, I'll analyze the relevant files in the context, particularly focusing on the chatbot implementation. Here's my step-by-step reasoning:

            1. I'll look for files related to the chatbot, such as 'chatbot.py' or similar.
            2. I'll examine the functions and classes defined in these files.
            3. I'll trace the flow of how a user query is processed.

            Based on the context provided, here's how the chatbot handles user queries:
            [Detailed explanation of the process]

            This process allows the chatbot to understand the context of the repository and provide relevant answers to user queries about the codebase.
            """

            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=f"You are an AI assistant specialized in analyzing GitHub repositories. Your responses should be clear, concise, and directly related to the repository content provided in the context. Here are some examples of how to respond:\n\n{few_shot_examples}\n\nWhen answering, please follow these steps:\n1. Analyze the relevant parts of the repository context.\n2. If the information is not directly available, state that clearly.\n3. Provide a step-by-step explanation of your reasoning.\n4. Summarize your findings in a concise answer.\n5. Maintain context from previous messages in the conversation."),
                MessagesPlaceholder(variable_name="history"),
                HumanMessage(content="{input}"),
                AIMessage(content="{output}")
            ])

            self.conversation_chain = LLMChain(
                llm=llm,
                prompt=prompt,
                memory=self.memory,
                verbose=True
            )
            logging.debug("Conversation chain initialized successfully")
        except Exception as e:
            logging.error(f"Error initializing conversation chain: {e}", exc_info=True)
            raise

    async def chat(self, query, context):
        try:
            logging.debug(f"Entering ChatSession.chat with query: {query}")
            
            if not self.conversation_chain:
                logging.debug("Initializing conversation chain")
                await self.initialize_conversation_chain(context)
            
            logging.debug("Running conversation chain")
            response = await self.conversation_chain.ainvoke({"input": f"Repository context:\n{json.dumps(context, indent=2)}\n\nUser question: {query}"})
            
            logging.debug(f"Chat response: {response}")
            return response['text']
        except Exception as e:
            logging.error(f"Error in ChatSession.chat: {e}", exc_info=True)
            raise

async def get_jamba_response(query, context):
    try:
        logging.debug(f"Entering get_jamba_response with query: {query}")
        logging.debug(f"API Key: {os.getenv('AI21_API_KEY')[:5]}...")

        # Initialize retrieval QA
        retrieval_qa = await initialize_retrieval_qa(context)
        logging.debug("Retrieval QA initialized successfully")

        # Use ChatSession for conversation
        context_string = json.dumps(context, sort_keys=True)
        session_id = hashlib.md5(context_string.encode()).hexdigest()

        if session_id not in chat_sessions:
            chat_sessions[session_id] = ChatSession()

        chat_session = chat_sessions[session_id]
        response = await chat_session.chat(query, context)
        logging.debug(f"Final response: {response}")

        return response
    except Exception as e:
        logging.error(f"Error in get_jamba_response: {e}")
        raise