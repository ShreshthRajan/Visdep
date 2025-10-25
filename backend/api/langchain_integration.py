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
from backend.api.data_storage import initialize_database, store_repository_metadata, store_ast_data, retrieve_chunks, FAISS_DIR
from backend.api.github_api import fetch_repo_content, fetch_repo_metadata
from backend.api.ast_parser import parse_code_to_ast
from langchain.prompts import MessagesPlaceholder
from backend.api.graph_generator import create_dependency_graph, get_subgraph_at_level
from backend.api.hybrid_retrieval import HybridRetriever, build_chunk_graph
from backend.api.reranker import CodeReranker, ContextAssembler, extract_citations_from_response
import networkx as nx
from sklearn.metrics.pairwise import cosine_similarity
from anthropic import Anthropic

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

from langchain.docstore.document import Document
from langchain_ai21 import AI21LLM, AI21Embeddings
from langchain_openai import OpenAIEmbeddings
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

# Ensure AI21 API key is set (only when actually using AI21, not during tests)
# This check is deferred to runtime to allow testing without API keys
# if not os.getenv("AI21_API_KEY"):
#     raise RuntimeError("AI21_API_KEY environment variable is not set")

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
    def __init__(self, repo_id: int = None):
        self.memory = ConversationBufferMemory(return_messages=True, memory_key="history")
        self.conversation_chain = None
        self.vector_store = None
        self.full_context = None
        self.hybrid_retriever = None  # Step 2
        self.chunk_graph = None  # Step 2
        self.reranker = None  # NEW: Step 3
        self.context_assembler = None  # NEW: Step 3
        self.claude_client = None  # NEW: Step 3
        self.repo_id = repo_id  # Task 2.2: For FAISS persistence

    async def initialize_conversation_chain(self, context):
        try:
            self.full_context = context
            # Task 2.2: Pass repo_id for FAISS persistence
            self.vector_store = await self.initialize_vector_store(context, repo_id=self.repo_id)
            self.dependency_graph = create_dependency_graph(context)

            # Step 2: Initialize hybrid retriever
            await self.initialize_hybrid_retriever(context)

            # NEW: Step 3 - Initialize reranker and context assembler
            self.reranker = CodeReranker()
            self.context_assembler = ContextAssembler(max_tokens=6000)
            logging.info("Reranker and context assembler initialized (Step 3)")

            # NEW: Step 3 - Initialize Claude client
            anthropic_key = os.getenv("ANTHROPIC_API_KEY")
            if anthropic_key:
                self.claude_client = Anthropic(api_key=anthropic_key)
                logging.info("Claude client initialized (Step 3) - will use Claude for chat")
                # No need for conversation_chain when using Claude
                self.conversation_chain = None
            else:
                # Fallback to AI21 for backward compatibility
                logging.warning("ANTHROPIC_API_KEY not set, falling back to AI21")
                llm = CustomAI21ChatLLM(api_key=os.getenv("AI21_API_KEY"))
                logging.debug(f"CustomAI21ChatLLM initialized with model: {llm.model}")

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
                logging.debug("Conversation chain initialized successfully with AI21")
        except Exception as e:
            logging.error(f"Error initializing conversation chain: {e}", exc_info=True)
            raise

    async def initialize_vector_store(self, context, repo_id: int = None):
        """
        Initialize vector store with code chunks

        Task 2.2: Loads persisted FAISS index from disk if available (saves ~2s)
        Falls back to rebuilding if index not found or corrupted

        Args:
            context: Chunk data
            repo_id: Repository ID for index persistence

        Returns:
            FAISS vector store
        """
        # Task 2.2: Try to load persisted FAISS index first
        if repo_id:
            faiss_path = f"{FAISS_DIR}/{repo_id}"
            if os.path.exists(faiss_path):
                try:
                    embeddings = OpenAIEmbeddings(
                        api_key=os.getenv("OPENAI_API_KEY"),
                        model="text-embedding-3-large"
                    )
                    vector_store = FAISS.load_local(faiss_path, embeddings, allow_dangerous_deserialization=True)
                    logging.info(f"Loaded FAISS index from disk: {faiss_path} (fast path)")
                    return vector_store
                except Exception as e:
                    logging.warning(f"Failed to load FAISS from disk: {e}, rebuilding...")

        # Build FAISS index from chunks (original logic)
        documents = []

        # Check if context has chunks (new format) or files (old format)
        # For backward compatibility during transition
        if context and isinstance(next(iter(context.values())), dict) and 'chunk_id' not in next(iter(context.values())):
            # Old format: file-level context
            # Fall back to old behavior
            logging.warning("Using old file-level context format")
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
                for chunk in chunks:
                    documents.append(Document(page_content=chunk, metadata={"source": file_path}))
        else:
            # New format: chunk-level context
            logging.info("Using new chunk-level context format")
            for chunk_id, chunk_data in context.items():
                if isinstance(chunk_data, dict) and 'code' in chunk_data:
                    # Format chunk for embedding
                    content = f"File: {chunk_data['file_path']}\n"
                    content += f"Type: {chunk_data['type']}\n"
                    content += f"Name: {chunk_data['name']}\n\n"
                    content += chunk_data['code']

                    metadata = {
                        "chunk_id": chunk_id,
                        "source": chunk_data['file_path'],
                        "type": chunk_data['type'],
                        "name": chunk_data['name'],
                        "start_line": chunk_data.get('start_line', 0),
                        "end_line": chunk_data.get('end_line', 0)
                    }

                    documents.append(Document(page_content=content, metadata=metadata))

        # Use OpenAI embeddings (Step 1 baseline)
        embeddings = OpenAIEmbeddings(
            api_key=os.getenv("OPENAI_API_KEY"),
            model="text-embedding-3-large"
        )

        logging.info(f"Creating FAISS index with {len(documents)} documents")
        vector_store = await FAISS.afrom_documents(documents, embeddings)

        # Task 2.2: Save FAISS index to disk for fast loading next time
        if repo_id:
            try:
                os.makedirs(FAISS_DIR, exist_ok=True)
                faiss_path = f"{FAISS_DIR}/{repo_id}"
                vector_store.save_local(faiss_path)
                logging.info(f"Saved FAISS index to disk: {faiss_path}")
            except Exception as e:
                logging.warning(f"Failed to save FAISS to disk: {e}, continuing anyway")

        return vector_store

    async def initialize_hybrid_retriever(self, context):
        """
        Initialize hybrid retriever for Step 2

        Builds:
        - BM25 index over chunks
        - Chunk-level dependency graph
        - Hybrid retriever combining all signals
        """
        # Extract chunks from context
        chunks_list = []

        # Check format
        if context and isinstance(next(iter(context.values())), dict):
            first_item = next(iter(context.values()))
            if 'chunk_id' in first_item:
                # New chunk format
                chunks_list = list(context.values())
            else:
                # Old file format - skip hybrid retrieval
                logging.warning("Old file format detected, hybrid retrieval disabled")
                self.hybrid_retriever = None
                self.chunk_graph = None
                return

        if not chunks_list:
            logging.warning("No chunks available for hybrid retrieval")
            self.hybrid_retriever = None
            self.chunk_graph = None
            return

        # Build chunk-level graph
        logging.info("Building chunk-level dependency graph...")
        self.chunk_graph = build_chunk_graph(chunks_list)

        # Initialize hybrid retriever
        logging.info("Initializing hybrid retriever...")
        self.hybrid_retriever = HybridRetriever(
            chunks=chunks_list,
            vector_store=self.vector_store,
            chunk_graph=self.chunk_graph
        )

        logging.info("Hybrid retriever initialized successfully")

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

    def get_relevant_nodes(self, query: str, query_type: str) -> List[str]:
        try:
            if query_type == 'codebase':
                return list(self.dependency_graph.nodes())
            elif query_type == 'directory':
                directories = [node for node, data in self.dependency_graph.nodes(data=True) if data['type'] == 'directory']
                if not directories:
                    return []
                most_relevant = max(directories, key=lambda d: self.calculate_relevance(d, query))
                return list(nx.descendants(self.dependency_graph, most_relevant))
            elif query_type == 'file':
                files = [node for node, data in self.dependency_graph.nodes(data=True) if data['type'] == 'file']
                if not files:
                    return []
                most_relevant = max(files, key=lambda f: self.calculate_relevance(f, query))
                return [most_relevant] + list(self.dependency_graph.successors(most_relevant))
            elif query_type == 'function':
                functions = [node for node, data in self.dependency_graph.nodes(data=True) if data['type'] == 'import']
                if not functions:
                    return []
                most_relevant = max(functions, key=lambda f: self.calculate_relevance(f, query))
                return [most_relevant] + list(self.dependency_graph.predecessors(most_relevant)) + list(self.dependency_graph.successors(most_relevant))
            else:
                # For general queries, use a combination of vector similarity and graph centrality
                relevant_docs = self.vector_store.similarity_search(query, k=200)
                central_nodes = sorted(nx.pagerank(self.dependency_graph).items(), key=lambda x: x[1], reverse=True)[:20]
                return list(set([doc.metadata['source'] for doc in relevant_docs] + [node for node, _ in central_nodes]))
        except Exception as e:
            logging.error(f"Error in get_relevant_nodes: {e}")
            return []

    def classify_query(self, query: str) -> str:
        query_lower = query.lower()
        if any(word in query_lower for word in ['entire', 'whole', 'all', 'codebase', 'repository']):
            return 'codebase'
        elif 'directory' in query_lower or 'folder' in query_lower:
            return 'directory'
        elif 'file' in query_lower:
            return 'file'
        elif 'function' in query_lower or 'method' in query_lower or 'class' in query_lower:
            return 'function'
        else:
            return 'general'
    def get_max_tokens(self, query_type: str) -> int:
        if query_type == 'codebase':
            return 8000
        elif query_type == 'directory':
            return 6000
        elif query_type == 'file':
            return 4000
        elif query_type == 'function':
            return 2000
        else:
            return 6000
        
    def calculate_relevance(self, node: str, query: str) -> float:
        try:
            node_embedding = self.vector_store.embeddings.embed_query(node)
            query_embedding = self.vector_store.embeddings.embed_query(query)
            similarity = cosine_similarity([node_embedding], [query_embedding])[0][0]
            centrality = nx.pagerank(self.dependency_graph).get(node, 0)  # Default to 0 if node not in pagerank
            return similarity * 0.7 + centrality * 0.3
        except Exception as e:
            logging.error(f"Error calculating relevance: {e}")
            return 0  # Return a default value in case of error
                
    def get_relevant_context(self, query: str) -> str:
        """
        Get relevant context for query

        NEW (Step 2): Uses hybrid retrieval if available
        OLD: Falls back to file-level retrieval
        """
        # NEW: Use hybrid retriever if initialized
        if self.hybrid_retriever:
            return self._get_context_with_hybrid(query)

        # OLD: Fallback to original method
        return self._get_context_legacy(query)

    def _get_context_with_hybrid(self, query: str) -> str:
        """
        NEW: Get context using hybrid retrieval (Step 2)

        Uses: BM25 + vector + graph expansion + multi-factor ranking
        """
        logging.info("Using hybrid retrieval for context")

        # Detect query complexity
        query_lower = query.lower()
        is_complex = any(word in query_lower for word in
                        ['complete', 'entire', 'all', 'flow', 'trace', 'execution', 'how does'])

        # Adjust retrieval based on complexity
        if is_complex or len(query.split()) > 15:
            # Complex query: retrieve more chunks
            top_k = 40
            expand_max = 50
        else:
            # Simple query: standard retrieval
            top_k = 20
            expand_max = 30

        # Use hybrid search
        top_chunks = self.hybrid_retriever.hybrid_search(
            query=query,
            top_k=top_k,
            expand=True,
            expand_max=expand_max
        )

        # Format chunks for LLM
        all_context = []
        total_tokens = 0
        max_tokens = 6000

        for chunk in top_chunks:
            content = f"## {chunk['file_path']}:{chunk['start_line']}-{chunk['end_line']} - {chunk['name']}\n"
            content += f"Type: {chunk['type']}\n\n"
            content += f"```\n{chunk['code']}\n```\n\n"

            content_tokens = len(content.split())
            if total_tokens + content_tokens > max_tokens:
                break

            all_context.append(content)
            total_tokens += content_tokens

        logging.info(f"Hybrid retrieval returned {len(all_context)} chunks ({total_tokens} tokens)")
        return "\n".join(all_context)

    def _get_context_legacy(self, query: str) -> str:
        """
        OLD: Original file-level context retrieval (backward compatibility)
        """
        logging.warning("Using legacy file-level retrieval")

        query_type = self.classify_query(query)
        relevant_nodes = self.get_relevant_nodes(query, query_type)

        all_context = []
        total_tokens = 0
        max_tokens = self.get_max_tokens(query_type)

        for node in relevant_nodes:
            if node in self.full_context:
                file_info = self.full_context[node]
                content = f"File: {node}\n\n"
                if isinstance(file_info, dict):
                    if 'content' in file_info:
                        content += file_info['content'] + "\n\n"
                    if 'functions' in file_info:
                        content += f"Functions: {', '.join(file_info['functions'])}\n"
                    if 'classes' in file_info:
                        content += f"Classes: {', '.join(file_info['classes'])}\n"
                    if 'imports' in file_info:
                        content += f"Imports: {', '.join(file_info['imports'])}\n"

                content_tokens = len(content.split())
                if total_tokens + content_tokens > max_tokens:
                    break

                all_context.append(content)
                total_tokens += content_tokens

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
        """
        Chat with LLM using retrieved context (batch mode)

        NEW (Step 3): Uses Claude + reranking + smart context assembly
        OLD: Falls back to AI21 if Claude not available
        """
        try:
            # NEW: Use Claude if available (even without hybrid retriever)
            if self.claude_client:
                # If hybrid retriever available, use full pipeline
                if self.hybrid_retriever and self.reranker:
                    return await self._chat_with_claude(query)
                else:
                    # Claude available but hybrid not (old context format)
                    # Use Claude with legacy retrieval
                    return await self._chat_with_claude_legacy(query)

            # OLD: Fallback to original AI21 flow
            return await self._chat_legacy(query)

        except Exception as e:
            logging.error(f"Error in ChatSession.chat: {e}", exc_info=True)
            raise

    async def chat_stream(self, query: str):
        """
        Task 2.3: Streaming variant of chat()

        Yields tokens as they're generated for better perceived latency.
        Same quality, same answer, just streamed delivery.
        """
        try:
            # Only streaming supported for Claude with hybrid retriever
            if self.claude_client and self.hybrid_retriever and self.reranker:
                async for token in self._chat_with_claude_stream(query):
                    yield token
            else:
                # Fallback: stream the batch response (simulate streaming)
                response = await self.chat(query)
                # Yield in chunks for consistent interface
                for i in range(0, len(response), 50):
                    yield response[i:i+50]
                    await asyncio.sleep(0.01)  # Small delay to simulate streaming

        except Exception as e:
            logging.error(f"Error in ChatSession.chat_stream: {e}", exc_info=True)
            yield f"Error: {str(e)}"

    def _calculate_dynamic_token_budget(self, is_complex: bool) -> int:
        """
        Calculate token budget dynamically based on query complexity and repository size

        Args:
            is_complex: Whether query is complex (from query analysis)

        Returns:
            max_tokens: Dynamic token budget

        Formula:
            base (6K) × complexity (1-2x) × repo_size (0.5-3x) = 3K-36K tokens
        """
        # Base budget
        base_budget = 6000

        # Complexity multiplier
        complexity_multiplier = 2.0 if is_complex else 1.0

        # Repo size multiplier (scales with total chunks available)
        total_chunks = len(self.hybrid_retriever.chunks) if self.hybrid_retriever else 100
        repo_size_multiplier = min(3.0, total_chunks / 100.0)
        repo_size_multiplier = max(0.5, repo_size_multiplier)  # Minimum 0.5x

        # Calculate budget
        max_tokens = int(base_budget * complexity_multiplier * repo_size_multiplier)

        # Cap at Claude's context limit (leave room for response)
        # Claude 4.0 has 200K context, cap at 150K to leave 50K for response
        max_tokens = min(max_tokens, 150000)

        logging.info(f"Dynamic token budget: {max_tokens} (chunks={total_chunks}, complex={is_complex})")
        return max_tokens

    async def _chat_with_claude_stream(self, query: str):
        """
        Task 2.3: Streaming variant of _chat_with_claude()

        Yields tokens as Claude generates them for better UX.
        Same quality, same answer, just streamed delivery.
        """
        logging.info("Using Claude with full retrieval pipeline (STREAMING)")

        # Detect query complexity (same as batch)
        query_lower = query.lower()
        is_complex = any(word in query_lower for word in
                        ['complete', 'entire', 'all', 'flow', 'trace', 'execution', 'how does'])

        logging.info(f"Query complexity: {'complex' if is_complex else 'simple'}")

        # Hybrid search + reranking (same as batch)
        top_chunks = self.hybrid_retriever.hybrid_search(
            query=query,
            top_k=20,
            expand=True,
            expand_max=30
        )

        if not top_chunks:
            yield "I couldn't find relevant information in the codebase to answer your question."
            return

        # Rerank
        rerank_k = 20 if is_complex else 10
        reranked_chunks = self.reranker.rerank(query, top_chunks, top_k=rerank_k)

        # Assemble context
        max_tokens = self._calculate_dynamic_token_budget(is_complex)
        avg_tokens_per_chunk = 500
        include_full = min(len(reranked_chunks), max_tokens // avg_tokens_per_chunk, 30)

        self.context_assembler.max_tokens = max_tokens
        assembled = self.context_assembler.assemble_context(
            reranked_chunks,
            include_full_code_top_n=include_full
        )

        context_text = "\n".join(assembled['context_parts'])

        # Build prompt
        prompt = self._build_claude_prompt(query, context_text, assembled)

        # Stream Claude response
        async for token in self._query_claude_stream(prompt):
            yield token

    async def _chat_with_claude(self, query: str) -> str:
        """
        NEW: Chat using Claude with full Step 1-3 pipeline

        Flow:
        1. Hybrid search (Step 2)
        2. Cross-encoder reranking (Step 3)
        3. Context assembly (Step 3)
        4. Claude LLM (Step 3)
        5. Citation extraction (Step 3)
        """
        logging.info("Using Claude with full retrieval pipeline (Steps 1-3)")

        # Detect query complexity
        query_lower = query.lower()
        is_complex = any(word in query_lower for word in
                        ['complete', 'entire', 'all', 'flow', 'trace', 'execution', 'how does'])

        logging.info(f"Query complexity: {'complex' if is_complex else 'simple'}")

        # Step 1: Hybrid search (gets top 20 chunks)
        top_chunks = self.hybrid_retriever.hybrid_search(
            query=query,
            top_k=20,
            expand=True,
            expand_max=30
        )

        if not top_chunks:
            return "I couldn't find relevant information in the codebase to answer your question."

        logging.info(f"Hybrid search returned {len(top_chunks)} chunks")

        # Step 2: Rerank (adjust based on complexity)
        rerank_k = 20 if is_complex else 10
        reranked_chunks = self.reranker.rerank(query, top_chunks, top_k=rerank_k)
        logging.info(f"Reranked to top {len(reranked_chunks)} chunks")

        # Step 3: Assemble context with DYNAMIC token budget
        max_tokens = self._calculate_dynamic_token_budget(is_complex)

        # Calculate dynamic include_full based on budget (not static 5/10)
        # With tiktoken: formatted chunks (code + markdown) ≈ 500 tokens
        # This accounts for markdown overhead (##, ```, **Type:**, etc.)
        avg_tokens_per_chunk = 500
        include_full = min(len(reranked_chunks), max_tokens // avg_tokens_per_chunk, 30)
        logging.info(f"Dynamic include_full: {include_full} (budget={max_tokens}, chunks={len(reranked_chunks)}, avg={avg_tokens_per_chunk})")

        # Update context assembler budget
        self.context_assembler.max_tokens = max_tokens

        assembled = self.context_assembler.assemble_context(
            reranked_chunks,
            include_full_code_top_n=include_full
        )

        context_text = "\n".join(assembled['context_parts'])
        logging.info(f"Assembled context: {assembled['chunks_included']} chunks, {assembled['total_tokens']} tokens")

        # Step 4: Build prompt for Claude
        prompt = self._build_claude_prompt(query, context_text, assembled)

        # Step 5: Query Claude
        response_text = await self._query_claude(prompt)

        # Step 6: Extract citations from response
        citations = extract_citations_from_response(response_text)

        # Step 7: Format response with metadata
        # For now, just return text (metadata will be used by frontend later)
        logging.info(f"Claude response generated ({len(response_text)} chars, {len(citations)} citations)")

        return response_text

    async def _chat_with_claude_legacy(self, query: str) -> str:
        """
        Use Claude with old file-level context (no hybrid retrieval)

        This handles the case where:
        - Claude is available
        - But context is old file-level format
        - So hybrid retrieval is disabled
        """
        logging.info("Using Claude with legacy file-level context")

        # Use old retrieval method
        relevant_context = self._get_context_legacy(query)

        # Build simple prompt
        prompt = f"""You are an expert software engineer analyzing a codebase.

RELEVANT CODE:
{relevant_context}

USER QUESTION:
{query}

INSTRUCTIONS:
- Answer based on the code above
- Reference files when possible
- Be concise and accurate

Your answer:"""

        # Query Claude
        response_text = await self._query_claude(prompt)

        return response_text

    async def _chat_legacy(self, query: str) -> str:
        """
        OLD: Original chat flow with AI21 (backward compatibility)
        """
        logging.warning("Using legacy AI21 chat flow")

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

    def _build_claude_prompt(self, query: str, context_text: str, assembled: Dict) -> str:
        """
        Build structured prompt for Claude

        Args:
            query: User query
            context_text: Assembled context
            assembled: Assembly metadata

        Returns:
            Formatted prompt string
        """
        # Get conversation history
        history_messages = self.memory.load_memory_variables({})
        history = history_messages.get('history', [])

        prompt = f"""You are an expert software engineer analyzing a codebase. Your role is to help developers understand the code by providing clear, accurate, and insightful explanations.

RELEVANT CODE CONTEXT:
{context_text}

"""

        # Add conversation history if exists
        if history:
            prompt += "CONVERSATION HISTORY:\n"
            for msg in history[-4:]:  # Last 4 messages
                role = "User" if hasattr(msg, 'type') and msg.type == "human" else "Assistant"
                content = msg.content if hasattr(msg, 'content') else str(msg)
                prompt += f"{role}: {content}\n"
            prompt += "\n"

        prompt += f"""USER QUESTION:
{query}

INSTRUCTIONS:
1. Answer based on the provided code context above
2. Reference specific files and line numbers when discussing code (format: file.py:42-68)
3. If the context doesn't contain enough information, say so clearly
4. Be concise but thorough
5. Use a confident, knowledgeable tone (like a senior engineer explaining to a teammate)

Your answer:"""

        return prompt

    async def _query_claude(self, prompt: str) -> str:
        """
        Query Claude 4.0 Sonnet (batch mode)

        Args:
            prompt: Formatted prompt

        Returns:
            Claude's response
        """
        try:
            # Use Claude 4.0 Sonnet (batch mode)
            response = self.claude_client.messages.create(
                model="claude-sonnet-4-20250514",  # Claude 4.0 Sonnet (latest)
                max_tokens=2000,
                temperature=0.3,  # Lower temp for more factual responses
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            # Extract text from response
            response_text = response.content[0].text

            # Save to conversation memory
            self.memory.save_context(
                {"input": prompt},
                {"output": response_text}
            )

            return response_text

        except Exception as e:
            logging.error(f"Error querying Claude: {e}")
            raise

    async def _query_claude_stream(self, prompt: str):
        """
        Query Claude 4.0 Sonnet (streaming mode) - Task 2.3

        Streams tokens as they're generated for better perceived latency.
        Actual latency same as batch, but user sees first token in ~1s.

        Args:
            prompt: Formatted prompt

        Yields:
            Token chunks from Claude
        """
        try:
            # Use Claude 4.0 Sonnet with streaming
            full_response = ""

            with self.claude_client.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    yield text

            # Save complete response to conversation memory
            self.memory.save_context(
                {"input": prompt},
                {"output": full_response}
            )

        except Exception as e:
            logging.error(f"Error in Claude streaming: {e}")
            yield f"Error: {str(e)}"

async def get_jamba_response_stream(query: str, context: Dict[str, Any], repo_id: int = None):
    """
    Task 2.3: Streaming variant of get_jamba_response()

    Yields tokens as they're generated. No caching for streams (live only).

    Args:
        query: User query
        context: Code context
        repo_id: Repository ID

    Yields:
        Response tokens
    """
    try:
        logging.debug(f"Entering streaming query with: {query}")

        # Build session (same as batch)
        context_string = json.dumps(context, sort_keys=True)
        session_id = hashlib.md5(context_string.encode()).hexdigest()

        if session_id not in chat_sessions:
            chat_sessions[session_id] = ChatSession(repo_id=repo_id)
            await chat_sessions[session_id].initialize_conversation_chain(context)

        chat_session = chat_sessions[session_id]

        # Stream the response
        async for token in chat_session.chat_stream(query):
            yield token

    except Exception as e:
        logging.error(f"Error in streaming response: {e}")
        yield f"Error: {str(e)}"


async def get_jamba_response(query: str, context: Dict[str, Any], repo_id: int = None) -> str:
    try:
        logging.debug(f"Entering get_jamba_response with query: {query}")
        logging.debug(f"API Key: {os.getenv('AI21_API_KEY')[:5] if os.getenv('AI21_API_KEY') else 'Not set'}...")

        # Task 2.1: Check cache first (if repo_id available)
        if repo_id:
            from backend.api.data_storage import get_cached_response, store_cached_response
            cached = get_cached_response(query, repo_id)
            if cached:
                logging.info(f"Cache HIT for query (repo_id={repo_id})")
                return cached
            logging.debug(f"Cache MISS for query (repo_id={repo_id})")

        # NEW: Load chunks from database if available
        # For now, use context as-is (it might be old file-level or new chunk-level)
        # Future: Always load from DB
        context_string = json.dumps(context, sort_keys=True)
        session_id = hashlib.md5(context_string.encode()).hexdigest()

        if session_id not in chat_sessions:
            # Task 2.2: Pass repo_id to ChatSession for FAISS persistence
            chat_sessions[session_id] = ChatSession(repo_id=repo_id)
            # Convert context to chunk format if it's chunks from DB
            # For Step 1: context is still file-level from frontend
            # Vector store will handle both formats
            await chat_sessions[session_id].initialize_conversation_chain(context)

        chat_session = chat_sessions[session_id]
        response = await chat_session.chat(query)
        logging.debug(f"Final response: {response}")

        # Task 2.1: Store in cache after generating (if repo_id available)
        if repo_id and response:
            from backend.api.data_storage import store_cached_response
            store_cached_response(query, repo_id, response)
            logging.debug(f"Cached response for future queries (repo_id={repo_id})")

        return response
    except Exception as e:
        logging.error(f"Error in get_jamba_response: {e}")
        raise
