# backend/api/langchain_integration.py
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
from langchain.text_splitter import RecursiveCharacterTextSplitter

from langchain.schema.runnable.history import RunnableWithMessageHistory
from langchain.memory.chat_message_histories import ChatMessageHistory
from langchain.schema import BaseMemory, BaseChatMessageHistory
from langchain.schema.messages import AIMessage, HumanMessage
from langchain.schema.messages import BaseMessage
from langchain.chains import LLMChain
from langchain.llms.base import LLM
from langchain.callbacks.manager import CallbackManagerForLLMRun
from typing import Dict, Any, List, Mapping, Optional
from langchain.prompts import SystemMessagePromptTemplate, HumanMessagePromptTemplate

# Load environment variables from .env file
load_dotenv()

# Ensure AI21 API key is set
if not os.getenv("AI21_API_KEY"):
    raise RuntimeError("AI21_API_KEY environment variable is not set")

def fetch_parse_store_repo(repo_url, auth_token):
    try:
        repo_content = fetch_repo_content(repo_url, auth_token)
        repo_metadata = fetch_repo_metadata(repo_url, auth_token)
        repo_name = repo_metadata.get('full_name')
        repo_id = store_repository_metadata(repo_name, repo_metadata)
        ast_data = parse_code_to_ast(repo_content)
        
        full_context = {}
        for file_info in repo_content:
            file_path = file_info['path']
            full_context[file_path] = {
                'content': file_info['content'],
                **ast_data.get(file_path, {})
            }
        
        for file_path, file_info in ast_data.items():
            store_ast_data(repo_id, file_path, file_info)
        
        return repo_id, full_context
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
        self.vector_store = None
        self.full_context = None

    async def initialize_conversation_chain(self, context):
        try:
            logging.debug("Initializing CustomAI21ChatLLM")
            llm = CustomAI21ChatLLM(api_key=os.getenv("AI21_API_KEY"))
            logging.debug(f"CustomAI21ChatLLM initialized with model: {llm.model}")
            
            self.full_context = context
            self.vector_store = await self.initialize_vector_store(context)

            prompt = ChatPromptTemplate(
                messages=[
                    SystemMessagePromptTemplate.from_template(self.get_system_message()),
                    MessagesPlaceholder(variable_name="history"),
                    HumanMessagePromptTemplate.from_template("{input}")
                ]
            )

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

    async def initialize_vector_store(self, context):
        documents = []
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=400,
            separators=["\n\n", "\n", " ", ""]
        )
        for file_path, file_info in context.items():
            content = f"File: {file_path}\n\n"
            if isinstance(file_info, dict) and 'content' in file_info:
                content += file_info['content'] + "\n\n"
            if isinstance(file_info, dict):
                for key, value in file_info.items():
                    if key != 'content':
                        if isinstance(value, list):
                            content += f"{key}: {', '.join(value)}\n"
                        else:
                            content += f"{key}: {value}\n"
            chunks = text_splitter.split_text(content)
            documents.extend(chunks)
        
        embeddings = AI21Embeddings(api_key=os.getenv("AI21_API_KEY"))
        return await FAISS.afrom_texts(documents, embeddings)

    def get_system_message(self):
        return """You are an AI assistant specialized in analyzing GitHub repositories. Your task is to provide clear, concise, and accurate information about the repository's content and structure. When answering:
    1. Always base your responses on the repository context provided, including file contents when necessary.
    2. Be confident and affirmative in your responses. Your tone should be a 10 year veteran L6 engineering manager. 
    3. Provide step-by-step reasoning for complex queries.
    4. If asked about a specific file, function, or feature, focus on that in your response and refer to the actual code if available.
    5. Maintain context from previous messages in the conversation.
    6. Infer the purpose and functionality of code based on file names, functions, imports, and actual code content.
    9. Consider the overall structure of the repository, including directories and file organization.
    11. When discussing the purpose of the repository, review the entire codebase, including file contents and the readme.md file, and provide a concise, specific outline of the codebase. 
    """

    def get_relevant_context(self, query: str) -> str:
        relevant_docs = self.vector_store.similarity_search_with_score(query, k=200)  # Reduced from 100
        sorted_docs = sorted(relevant_docs, key=lambda x: x[1], reverse=True)
        
        all_context = []
        total_tokens = 0
        max_tokens = 6000  # Reduced from 8000

        for doc, score in sorted_docs:
            doc_content = doc.page_content
            doc_tokens = len(doc_content.split())
            
            if total_tokens + doc_tokens > max_tokens:
                break
            
            all_context.append(doc_content)
            total_tokens += doc_tokens

        return "\n\n".join(all_context)
    def get_full_context_summary(self) -> str:
        summary = "Repository Overview:\n"
        for file_path, file_info in self.full_context.items():
            summary += f"- {file_path}\n"
            if isinstance(file_info, dict):
                if 'type' in file_info:
                    summary += f"  Type: {file_info['type']}\n"
                if 'functions' in file_info:
                    summary += f"  Functions: {', '.join(file_info['functions'])}\n"
                if 'classes' in file_info:
                    summary += f"  Classes: {', '.join(file_info['classes'])}\n"
                if 'content' in file_info:
                    summary += f"  Content Preview: {file_info['content'][:100]}...\n"
        return summary

    async def chat(self, query: str) -> str:
        try:
            if not self.conversation_chain:
                raise ValueError("Conversation chain not initialized. Please call initialize_conversation_chain first.")
            
            full_context_summary = self.get_full_context_summary()
            relevant_context = self.get_relevant_context(query)
        
            input_text = f"""Full Repository Context:
    {full_context_summary}

    Relevant Information:
    {relevant_context}

    User question: {query}

    Please follow these steps in your response without explicitly stating them:
    1. Analyze the question and identify the key points to address.
    2. Review the relevant information and full context summary.
    3. If asked about a specific file, refer to specific file contents to provide accurate information. If asked about the 'purpose' 'goal' or anything else about the entire repo or codebase, refer to the entire codebase.
    4. Provide a clear and concise answer based on your analysis, focusing on code-specific insights when applicable.
    5. If the information is not directly available in the context, say so and provide the most relevant information you can find or make an educated guess based on the available context.
    6. When discussing code, consider its structure, purpose, and how it fits into the overall project.
    7. For questions about the overall purpose or structure of the repository, consider all provided context to give a comprehensive answer.
    """

            response = await self.conversation_chain.ainvoke({"input": input_text})
            return response['text']
        except Exception as e:
            logging.error(f"Error in ChatSession.chat: {e}", exc_info=True)
            raise

async def get_jamba_response(query: str, context: Dict[str, Any]) -> str:
    try:
        logging.debug(f"Entering get_jamba_response with query: {query}")
        logging.debug(f"API Key: {os.getenv('AI21_API_KEY')[:5]}...")

        context_string = json.dumps(context, sort_keys=True)
        session_id = hashlib.md5(context_string.encode()).hexdigest()

        if session_id not in chat_sessions:
            chat_sessions[session_id] = ChatSession()
            await chat_sessions[session_id].initialize_conversation_chain(context)

        chat_session = chat_sessions[session_id]
        response = await chat_session.chat(query)
        logging.debug(f"Final response: {response}")

        return response
    except Exception as e:
        logging.error(f"Error in get_jamba_response: {e}")
        raise