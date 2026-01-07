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
from backend.api.graph_generator import create_dependency_graph, get_subgraph_at_level
from backend.api.hybrid_retrieval import HybridRetriever, build_chunk_graph
from backend.api.reranker import CodeReranker, ContextAssembler, extract_citations_from_response
from backend.api.query_enhancement import (
    expand_query_with_llm,
    decompose_query,
    agentic_retrieval_with_reflection,
    detect_primary_language,
    detect_query_intent_language,
    detect_query_intent_language_llm,
    enhance_query_multimodal
)
from backend.api.summarization import (
    load_summaries,
    retrieve_relevant_summaries
)
import networkx as nx
from sklearn.metrics.pairwise import cosine_similarity
from anthropic import Anthropic

# Initialize the database
initialize_database()

# Setup logging (INFO level to avoid Railway rate limit)
# DEBUG level causes excessive logs (100MB+ parsed_data dumps) → Railway 500 logs/sec limit
logging.basicConfig(level=logging.INFO)

# Ensure FAISS can be imported (with fallback for Railway's CPU without AVX-512)
try:
    import faiss
    logging.info("✅ FAISS imported successfully")
except ImportError as e:
    # Railway CPU may not have AVX-512 instructions, force basic FAISS
    logging.warning(f"⚠️ FAISS AVX-512 import failed, trying fallback: {e}")
    try:
        import os
        os.environ['FAISS_NO_AVX512'] = '1'
        import faiss
        logging.info("✅ FAISS imported with AVX-512 disabled")
    except ImportError as fallback_error:
        logging.error(f"❌ FAISS import failed completely: {fallback_error}")
        raise ImportError(f"FAISS import failed: {fallback_error}. Ensure faiss-cpu is installed.")

# LangChain v0.2+ imports (migrated from deprecated v0.1 paths)
from langchain_core.documents import Document
from langchain_core.prompts import (
    MessagesPlaceholder,
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate
)
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from langchain_core.runnables import RunnablePassthrough, RunnableSequence
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.language_models.llms import LLM
from langchain_core.callbacks import CallbackManagerForLLMRun

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS

# AI21 imports removed from module level - lazy loaded only when needed (fallback case)
# This prevents ImportError if langchain_ai21 version incompatible
from langchain_openai import OpenAIEmbeddings

from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain, ConversationChain, LLMChain
from langchain.memory import ConversationBufferMemory

from typing import Dict, Any, List, Mapping, Optional


class IndexingInProgressError(Exception):
    """
    Raised when query is attempted on a mega-repo that's still being indexed.

    Used to return a graceful message to the user instead of timing out.
    """
    pass

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


# =============================================================================
# FAISS PRE-LOADING: Download FAISS to local disk during startup
# =============================================================================
# This function is called during background pre-warming to ensure FAISS is
# available on local disk before the first query. Without this, the first
# query would need to stream-download 774MB FAISS (~90 seconds), exceeding
# Railway's request timeout.
#
# After pre-warming:
# - Local disk check: ~1 second
# - No streaming download needed
# - Query completes within timeout
# =============================================================================

async def prewarm_faiss_to_disk(repo_id: int) -> bool:
    """
    Pre-download FAISS index to local disk for fast query-time loading.

    This is called during background pre-warming for mega-repos. It downloads
    the FAISS index from Supabase Storage to local disk, so that the first
    query can use the fast local disk path instead of streaming download.

    Args:
        repo_id: Repository ID

    Returns:
        True if FAISS is available on local disk (either pre-existing or downloaded)
        False if download failed
    """
    import gzip
    import shutil
    import tempfile
    import httpx

    # Check if already exists on local disk
    faiss_path = f"{FAISS_DIR}/{repo_id}"
    if os.path.exists(faiss_path):
        logging.info(f"   ✅ FAISS already on disk: {faiss_path}")
        return True

    # Check if FAISS exists in Supabase Storage
    try:
        from backend.api.supabase_client import get_supabase_client
        supabase = get_supabase_client()

        result = supabase.table('repo_faiss')\
            .select('storage_path, chunk_count')\
            .eq('repo_id', repo_id)\
            .limit(1)\
            .execute()

        if not result.data or len(result.data) == 0:
            logging.info(f"   ℹ️ No FAISS in Storage for repo_id={repo_id} (will build on first query)")
            return False

        storage_path = result.data[0]['storage_path']
        chunk_count = result.data[0].get('chunk_count', 1)

        logging.info(f"   📥 Pre-loading FAISS from Storage: {storage_path} ({chunk_count} chunks)")

        # Download configuration
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_SERVICE_KEY')

        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}"
        }

        # Use persistent temp directory for entire operation
        with tempfile.TemporaryDirectory() as tmpdir:
            compressed_path = os.path.join(tmpdir, f"{repo_id}_compressed.gz")

            if chunk_count > 1:
                # PHASE 1: Parallel download chunks directly to temp files (memory-safe)
                logging.info(f"      ⚡ STREAMING {chunk_count} chunks to disk...")
                base_path = storage_path.rsplit('.chunk000', 1)[0] if '.chunk000' in storage_path else storage_path.rsplit('.faiss.gz', 1)[0] + '.faiss.gz'

                async def download_chunk_to_file(chunk_index: int) -> str:
                    """Stream download chunk directly to temp file"""
                    chunk_path = f"{base_path}.chunk{chunk_index:03d}"
                    download_url = f"{supabase_url}/storage/v1/object/repo-data/{chunk_path}"
                    temp_chunk_path = os.path.join(tmpdir, f"chunk_{chunk_index:03d}")

                    async with httpx.AsyncClient(timeout=300.0) as async_client:
                        async with async_client.stream('GET', download_url, headers=headers) as response:
                            if response.status_code != 200:
                                raise Exception(f"Failed to download chunk {chunk_index+1}: {response.status_code}")

                            bytes_written = 0
                            with open(temp_chunk_path, 'wb') as f:
                                async for data in response.aiter_bytes(chunk_size=8*1024*1024):
                                    f.write(data)
                                    bytes_written += len(data)

                            return temp_chunk_path

                # Parallel downloads with concurrency limit
                MAX_CONCURRENT = 5
                semaphore = asyncio.Semaphore(MAX_CONCURRENT)

                async def download_with_semaphore(chunk_index: int) -> str:
                    async with semaphore:
                        return await download_chunk_to_file(chunk_index)

                # Execute parallel downloads
                download_tasks = [download_with_semaphore(i) for i in range(chunk_count)]
                temp_chunk_paths = await asyncio.gather(*download_tasks)

                # PHASE 2: Concatenate temp files on disk
                logging.info(f"      📎 Concatenating {chunk_count} chunks on disk...")
                total_bytes = 0
                with open(compressed_path, 'wb') as outfile:
                    for temp_path in temp_chunk_paths:
                        with open(temp_path, 'rb') as infile:
                            while True:
                                chunk_data = infile.read(64*1024*1024)
                                if not chunk_data:
                                    break
                                outfile.write(chunk_data)
                                total_bytes += len(chunk_data)
                        os.unlink(temp_path)

                logging.info(f"      ✅ Concatenated {total_bytes/(1024*1024):.1f}MB to disk")

            else:
                # Single file - stream directly to disk
                download_url = f"{supabase_url}/storage/v1/object/repo-data/{storage_path}"

                async with httpx.AsyncClient(timeout=300.0) as async_client:
                    async with async_client.stream('GET', download_url, headers=headers) as response:
                        if response.status_code != 200:
                            raise Exception(f"Failed to download: {response.status_code}")

                        total_bytes = 0
                        with open(compressed_path, 'wb') as f:
                            async for data in response.aiter_bytes(chunk_size=8*1024*1024):
                                f.write(data)
                                total_bytes += len(data)

                logging.info(f"      ✅ Streamed {total_bytes/(1024*1024):.1f}MB to disk")

            # PHASE 3: Stream decompress on disk
            zip_path = os.path.join(tmpdir, f"{repo_id}.zip")
            compressed_size = os.path.getsize(compressed_path)
            logging.info(f"      📦 Stream decompressing {compressed_size/(1024*1024):.1f}MB...")

            with gzip.open(compressed_path, 'rb') as f_in:
                with open(zip_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out, length=64*1024*1024)

            os.unlink(compressed_path)

            decompressed_size = os.path.getsize(zip_path)
            logging.info(f"      📦 Decompressed to {decompressed_size/(1024*1024):.1f}MB")

            # PHASE 4: Extract and save to local disk
            extract_path = os.path.join(tmpdir, str(repo_id))
            shutil.unpack_archive(zip_path, extract_path)

            # Copy to persistent FAISS directory
            os.makedirs(FAISS_DIR, exist_ok=True)
            local_faiss_path = f"{FAISS_DIR}/{repo_id}"

            # Copy extracted files to FAISS directory
            if os.path.exists(local_faiss_path):
                shutil.rmtree(local_faiss_path)
            shutil.copytree(extract_path, local_faiss_path)

            logging.info(f"   ✅ FAISS pre-loaded to disk: {local_faiss_path}")
            return True

    except Exception as e:
        logging.warning(f"   ⚠️ FAISS pre-load failed for repo_id={repo_id}: {e}")
        import traceback
        logging.debug(traceback.format_exc())
        return False


async def initialize_retrieval_qa(context):
    """DEPRECATED - Old function, not used in current pipeline"""
    # Lazy import AI21 only if this function is called (which it isn't)
    from langchain_ai21 import AI21LLM, AI21Embeddings

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
        self.hierarchical_summaries = None  # HCGS: For full-repo understanding

    async def initialize_conversation_chain(self, context, skip_index_check: bool = False):
        """
        Initialize the conversation chain with vector store, hybrid retriever, etc.

        Args:
            context: Dict of chunk_id -> chunk data
            skip_index_check: If True, skip mega-repo index existence check.
                              Pass True for BACKGROUND INDEXING, False (default) for QUERIES.
        """
        try:
            self.full_context = context

            # =================================================================
            # MEGA-REPO GUARD: Check BEFORE expensive FAISS operations
            # =================================================================
            # CRITICAL FIX: This guard must run BEFORE initialize_vector_store()
            # to prevent queries from triggering 126K+ embedding rebuilds when
            # background indexing is still in progress or failed.
            #
            # Without this: Query → FAISS rebuild (126K embeddings) → rate limits → 500 error
            # With this: Query → Guard check → "Still indexing" message → user retries later
            # =================================================================
            MEGA_REPO_THRESHOLD = 50000  # 50K chunks = definitely needs pre-built indexes
            chunk_count = len(context) if context else 0

            if chunk_count > MEGA_REPO_THRESHOLD and self.repo_id and not skip_index_check:
                if not HybridRetriever.indexes_exist_in_storage(self.repo_id):
                    raise IndexingInProgressError(
                        f"🔄 This repository ({chunk_count:,} chunks) is still being indexed. "
                        "Please try again in 2-3 minutes. The graph visualization works while indexing completes."
                    )
                logging.info(f"✅ Mega-repo indexes verified for repo_id={self.repo_id} - proceeding with query")

            # Task 2.2: Pass repo_id for FAISS persistence
            self.vector_store = await self.initialize_vector_store(context, repo_id=self.repo_id)

            # =================================================================
            # MEGA-REPO OPTIMIZATION: Skip dependency_graph for large repos
            # =================================================================
            # create_dependency_graph() has O(n²) complexity in its directory-file
            # edge creation loop. For 152K chunks (Kubernetes), this causes:
            # - 10K directories × 20K files = 200 million operations
            # - Query hangs for 3+ minutes
            #
            # This is SAFE to skip for mega-repos because:
            # 1. Visual graph is pre-computed and stored in Supabase (separate)
            # 2. Hybrid retrieval uses chunk_graph, NOT dependency_graph
            # 3. dependency_graph is only used for legacy query classification
            # =================================================================
            SKIP_DEPENDENCY_GRAPH_THRESHOLD = 50000  # Same as MEGA_REPO_THRESHOLD
            chunk_count = len(context) if context else 0

            if chunk_count < SKIP_DEPENDENCY_GRAPH_THRESHOLD:
                self.dependency_graph = create_dependency_graph(context)
            else:
                self.dependency_graph = None
                logging.info(f"⚡ Skipping dependency_graph for mega-repo ({chunk_count:,} chunks) - using hybrid retrieval instead")

            # Step 2: Initialize hybrid retriever
            await self.initialize_hybrid_retriever(context, skip_index_check=skip_index_check)

            # NEW: Step 3 - Initialize reranker and context assembler
            self.reranker = CodeReranker()
            self.context_assembler = ContextAssembler(max_tokens=6000)
            logging.info("Reranker and context assembler initialized (Step 3)")
            
            # HCGS: Load hierarchical summaries for full-repo understanding
            if self.repo_id:
                self.hierarchical_summaries = load_summaries(self.repo_id)
                if self.hierarchical_summaries:
                    logging.info(f"✅ Loaded HCGS summaries: repo={bool(self.hierarchical_summaries.get('repo'))}, packages={len(self.hierarchical_summaries.get('packages', {}))}, files={len(self.hierarchical_summaries.get('files', {}))}")
                else:
                    logging.info("ℹ️ No pre-computed HCGS summaries available")

            # NEW: Step 3 - Initialize Claude client
            anthropic_key = os.getenv("ANTHROPIC_API_KEY")
            if anthropic_key:
                self.claude_client = Anthropic(api_key=anthropic_key)
                logging.info("Claude client initialized (Step 3) - will use Claude for chat")
                # No need for conversation_chain when using Claude
                self.conversation_chain = None
            else:
                # Fallback to AI21 for backward compatibility
                # Lazy import - only loads if Claude not available
                from langchain_ai21 import AI21LLM

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
        # Task 2.2: Try to load persisted FAISS index first (local disk, then Supabase Storage)
        if repo_id:
            # First try local disk
            faiss_path = f"{FAISS_DIR}/{repo_id}"
            if os.path.exists(faiss_path):
                try:
                    embeddings = OpenAIEmbeddings(
                        api_key=os.getenv("OPENAI_API_KEY"),
                        model="text-embedding-3-small"  # Must match creation model
                    )
                    vector_store = FAISS.load_local(faiss_path, embeddings, allow_dangerous_deserialization=True)
                    logging.info(f"✅ Loaded FAISS index from disk: {faiss_path} (fast path)")
                    return vector_store
                except Exception as e:
                    logging.warning(f"⚠️ Failed to load FAISS from disk: {e}, trying Supabase Storage...")
            
            # If local fails, try Supabase Storage
            try:
                from .supabase_client import get_supabase_client
                import gzip
                import shutil
                import tempfile
                import httpx
                
                supabase = get_supabase_client()
                
                # Check if FAISS exists in Supabase
                result = supabase.table('repo_faiss')\
                    .select('storage_path, chunk_count')\
                    .eq('repo_id', repo_id)\
                    .limit(1)\
                    .execute()
                
                if result.data and len(result.data) > 0:
                    storage_path = result.data[0]['storage_path']
                    chunk_count = result.data[0].get('chunk_count', 1)
                    logging.info(f"📥 Loading FAISS index from Supabase Storage: {storage_path} ({chunk_count} chunks)")
                    
                    # Download from Storage
                    supabase_url = os.getenv('SUPABASE_URL')
                    supabase_key = os.getenv('SUPABASE_SERVICE_KEY')
                    
                    headers = {
                        "apikey": supabase_key,
                        "Authorization": f"Bearer {supabase_key}"
                    }
                    
                    # =====================================================================
                    # STREAMING FAISS DOWNLOAD: Memory-efficient for mega-repos
                    # =====================================================================
                    # Problem: Old approach held compressed (774MB) + decompressed (774MB)
                    #          in memory simultaneously = 1.5GB peak → OOM on Railway
                    # Solution: Stream to disk, decompress on disk, peak memory ~64MB
                    # Speed: Parallel downloads maintained via concurrent temp file writes
                    # =====================================================================
                    # Note: asyncio is imported at top of file (line 8)

                    # Use persistent temp directory for entire operation
                    with tempfile.TemporaryDirectory() as tmpdir:
                        compressed_path = os.path.join(tmpdir, f"{repo_id}_compressed.gz")

                        if chunk_count > 1:
                            # PHASE 1: Parallel download chunks directly to temp files
                            # Memory: ~8MB per concurrent download (streaming buffer)
                            logging.info(f"   ⚡ STREAMING {chunk_count} chunks to disk (memory-safe)...")
                            base_path = storage_path.rsplit('.chunk000', 1)[0] if '.chunk000' in storage_path else storage_path.rsplit('.faiss.gz', 1)[0] + '.faiss.gz'

                            async def download_chunk_to_file(chunk_index: int) -> str:
                                """Stream download chunk directly to temp file - never holds full chunk in memory"""
                                chunk_path = f"{base_path}.chunk{chunk_index:03d}"
                                download_url = f"{supabase_url}/storage/v1/object/repo-data/{chunk_path}"
                                temp_chunk_path = os.path.join(tmpdir, f"chunk_{chunk_index:03d}")

                                async with httpx.AsyncClient(timeout=300.0) as async_client:
                                    # Use streaming response - writes to disk as data arrives
                                    async with async_client.stream('GET', download_url, headers=headers) as response:
                                        if response.status_code != 200:
                                            raise Exception(f"Failed to download chunk {chunk_index+1}: {response.status_code}")

                                        bytes_written = 0
                                        with open(temp_chunk_path, 'wb') as f:
                                            # 8MB streaming buffer - optimal for network I/O
                                            async for data in response.aiter_bytes(chunk_size=8*1024*1024):
                                                f.write(data)
                                                bytes_written += len(data)

                                        logging.info(f"   ✓ Chunk {chunk_index+1}/{chunk_count} → disk ({bytes_written/(1024*1024):.1f}MB)")
                                        return temp_chunk_path

                            # Parallel downloads with concurrency limit
                            MAX_CONCURRENT = 5
                            semaphore = asyncio.Semaphore(MAX_CONCURRENT)

                            async def download_with_semaphore(chunk_index: int) -> str:
                                async with semaphore:
                                    return await download_chunk_to_file(chunk_index)

                            # Execute parallel downloads to temp files
                            download_tasks = [download_with_semaphore(i) for i in range(chunk_count)]
                            temp_chunk_paths = await asyncio.gather(*download_tasks)

                            # PHASE 2: Concatenate temp files on disk (sequential, memory-efficient)
                            # Memory: 64MB buffer for disk-to-disk copy
                            logging.info(f"   📎 Concatenating {chunk_count} chunks on disk...")
                            total_bytes = 0
                            with open(compressed_path, 'wb') as outfile:
                                for i, temp_path in enumerate(temp_chunk_paths):
                                    with open(temp_path, 'rb') as infile:
                                        # 64MB buffer for optimal disk I/O
                                        while True:
                                            chunk_data = infile.read(64*1024*1024)
                                            if not chunk_data:
                                                break
                                            outfile.write(chunk_data)
                                            total_bytes += len(chunk_data)
                                    # Delete temp chunk immediately to free disk space
                                    os.unlink(temp_path)

                            logging.info(f"   ✅ Concatenated {total_bytes/(1024*1024):.1f}MB to disk")

                        else:
                            # Single file - stream directly to disk
                            download_url = f"{supabase_url}/storage/v1/object/repo-data/{storage_path}"
                            logging.info(f"   ⚡ STREAMING single file to disk...")

                            async with httpx.AsyncClient(timeout=300.0) as async_client:
                                async with async_client.stream('GET', download_url, headers=headers) as response:
                                    if response.status_code != 200:
                                        raise Exception(f"Failed to download: {response.status_code}")

                                    total_bytes = 0
                                    with open(compressed_path, 'wb') as f:
                                        async for data in response.aiter_bytes(chunk_size=8*1024*1024):
                                            f.write(data)
                                            total_bytes += len(data)

                                    logging.info(f"   ✅ Streamed {total_bytes/(1024*1024):.1f}MB to disk")

                        # =====================================================================
                        # PHASE 3: Stream decompress on disk (never holds both buffers in memory)
                        # Memory: 64MB buffer vs old approach's 1.5GB (compressed + decompressed)
                        # =====================================================================
                        zip_path = os.path.join(tmpdir, f"{repo_id}.zip")
                        compressed_size = os.path.getsize(compressed_path)
                        logging.info(f"   📦 Stream decompressing {compressed_size/(1024*1024):.1f}MB...")

                        with gzip.open(compressed_path, 'rb') as f_in:
                            with open(zip_path, 'wb') as f_out:
                                # 64MB buffer - optimal for gzip streaming
                                shutil.copyfileobj(f_in, f_out, length=64*1024*1024)

                        # Delete compressed file immediately to free disk space
                        os.unlink(compressed_path)

                        decompressed_size = os.path.getsize(zip_path)
                        logging.info(f"   📦 Decompressed to {decompressed_size/(1024*1024):.1f}MB (peak mem: ~64MB)")

                        # PHASE 4: Extract and load FAISS
                        extract_path = os.path.join(tmpdir, str(repo_id))
                        shutil.unpack_archive(zip_path, extract_path)

                        # Load FAISS from extracted directory
                        embeddings = OpenAIEmbeddings(
                            api_key=os.getenv("OPENAI_API_KEY"),
                            model="text-embedding-3-small"
                        )
                        vector_store = FAISS.load_local(extract_path, embeddings, allow_dangerous_deserialization=True)

                        # Save to local disk for future fast loading
                        os.makedirs(FAISS_DIR, exist_ok=True)
                        local_faiss_path = f"{FAISS_DIR}/{repo_id}"
                        vector_store.save_local(local_faiss_path)

                        logging.info(f"✅ Loaded FAISS from Supabase Storage and saved to disk: {local_faiss_path}")
                        return vector_store
                            
            except Exception as e:
                logging.warning(f"⚠️ Failed to load FAISS from Supabase Storage: {e}, rebuilding...")
                import traceback
                logging.debug(traceback.format_exc())

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

        # Use OpenAI embeddings with smaller, faster model
        # text-embedding-3-small: 5x faster, 5x cheaper, 98% quality of large model
        embeddings = OpenAIEmbeddings(
            api_key=os.getenv("OPENAI_API_KEY"),
            model="text-embedding-3-small"
        )

        logging.info(f"Creating FAISS index with {len(documents)} documents using parallel micro-batching")

        # STATE-OF-THE-ART: Parallel micro-batching optimized for method-level chunks
        # With method-level chunking (avg 300 tokens): Can use larger batches safely
        # BATCH_SIZE=300 guarantees safety: 300 docs × 800 tokens/doc = 240K tokens < 300K limit
        # Process batches in parallel (max 10 concurrent) for 10x speedup
        BATCH_SIZE = 300
        MAX_CONCURRENT = 10

        # Split documents into micro-batches
        batches = []
        for i in range(0, len(documents), BATCH_SIZE):
            batch = documents[i:i + BATCH_SIZE]
            batches.append(batch)

        total_batches = len(batches)
        logging.info(f"Processing {total_batches} micro-batches of {BATCH_SIZE} documents each (max {MAX_CONCURRENT} concurrent)...")

        async def process_batch(batch_docs, batch_num):
            """Process a single batch of documents into embeddings"""
            try:
                logging.info(f"⚡ Batch {batch_num}/{total_batches}: Embedding {len(batch_docs)} documents...")

                # Extract texts from documents
                texts = [doc.page_content for doc in batch_docs]

                # Get embeddings directly (bypasses FAISS internal batching)
                vectors = await embeddings.aembed_documents(texts)

                logging.info(f"✅ Batch {batch_num}/{total_batches}: Complete ({len(vectors)} embeddings)")
                return batch_docs, vectors

            except Exception as e:
                logging.error(f"❌ Batch {batch_num}/{total_batches}: Failed - {e}")
                raise

        # Process batches in parallel with concurrency limit
        all_docs = []
        all_vectors = []

        for i in range(0, total_batches, MAX_CONCURRENT):
            # Get next chunk of batches to process in parallel
            concurrent_batches = batches[i:i + MAX_CONCURRENT]
            batch_nums = range(i + 1, i + len(concurrent_batches) + 1)

            logging.info(f"🚀 Processing batches {i+1}-{i+len(concurrent_batches)} in parallel...")

            # Process batches concurrently
            tasks = [process_batch(batch, num) for batch, num in zip(concurrent_batches, batch_nums)]
            results = await asyncio.gather(*tasks)

            # Collect results
            for batch_docs, vectors in results:
                all_docs.extend(batch_docs)
                all_vectors.extend(vectors)

        logging.info(f"✅ All embeddings complete: {len(all_vectors)} vectors for {len(all_docs)} documents")

        # Build FAISS index from embeddings
        logging.info(f"🔧 Constructing FAISS index from embeddings...")
        texts = [doc.page_content for doc in all_docs]
        metadatas = [doc.metadata for doc in all_docs]

        # Use FAISS.from_embeddings() for direct construction
        text_embedding_pairs = list(zip(texts, all_vectors))
        vector_store = await FAISS.afrom_embeddings(
            text_embedding_pairs,
            embeddings,
            metadatas=metadatas
        )

        logging.info(f"✅ Successfully created FAISS index with {len(documents)} documents")

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

    async def initialize_hybrid_retriever(self, context, skip_index_check: bool = False):
        """
        Initialize hybrid retriever for Step 2

        Builds:
        - BM25 index over chunks
        - Chunk-level dependency graph
        - Hybrid retriever combining all signals

        Args:
            context: Dict of chunk_id -> chunk data
            skip_index_check: If True, skip the mega-repo index existence check.
                              Use this for BACKGROUND INDEXING which needs to BUILD
                              indexes that don't exist yet. Default False to protect
                              user QUERIES from timeout on unindexed mega-repos.
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

        # MEGA-REPO GUARD: For very large repos, check if indexes exist before building
        # This prevents 100+ second timeouts when querying repos still being indexed
        # SKIP this check during background indexing (skip_index_check=True)
        MEGA_REPO_THRESHOLD = 50000  # 50K chunks = definitely needs pre-built indexes
        is_mega_repo = len(chunks_list) > MEGA_REPO_THRESHOLD

        if is_mega_repo and self.repo_id and not skip_index_check:
            if not HybridRetriever.indexes_exist_in_storage(self.repo_id):
                raise IndexingInProgressError(
                    f"This repository ({len(chunks_list):,} chunks) is still being indexed. "
                    "Please try again in 2-3 minutes."
                )
            logging.info(f"✅ Mega-repo indexes found in Storage for repo_id={self.repo_id}")
        elif is_mega_repo and skip_index_check:
            logging.info(f"⚙️ Background indexing mode: Skipping index check for mega-repo ({len(chunks_list):,} chunks)")

        # =================================================================
        # CHUNK GRAPH: Load from cache or build
        # =================================================================
        # For mega-repos (152K chunks), building chunk_graph takes 30-60s.
        # Loading from cache takes <5s. Try cache first for mega-repos.
        # =================================================================
        self.chunk_graph = None

        if self.repo_id and is_mega_repo:
            # Try to load cached chunk_graph (30-60s savings for mega-repos)
            logging.info(f"📊 Attempting to load cached chunk_graph for mega-repo...")
            self.chunk_graph = HybridRetriever.load_chunk_graph_from_storage(self.repo_id)

        if self.chunk_graph is None:
            # Build chunk_graph (fast for small repos, needed for uncached mega-repos)
            logging.info("Building chunk-level dependency graph...")
            self.chunk_graph = build_chunk_graph(chunks_list)

        # Initialize hybrid retriever
        logging.info("Initializing hybrid retriever...")
        self.hybrid_retriever = HybridRetriever(
            chunks=chunks_list,
            vector_store=self.vector_store,
            chunk_graph=self.chunk_graph,
            repo_id=self.repo_id  # Enable loading cached indexes from Supabase
        )

        # =================================================================
        # FIX 1: Save indexes after on-demand build (for ALL repos)
        # =================================================================
        # If BM25/PageRank were built fresh (not loaded from cache), save them
        # to Supabase Storage for persistence across Railway restarts.
        # This ensures ALL repos (not just >5K chunks) have persistent indexes.
        # =================================================================
        if self.repo_id and not self.hybrid_retriever.bm25_loaded_from_cache:
            try:
                logging.info(f"💾 Saving newly-built indexes to Supabase Storage for repo_id={self.repo_id}")
                self.hybrid_retriever.save_indexes(self.repo_id, self.vector_store)
            except Exception as save_err:
                # Non-fatal: query can proceed even if save fails
                logging.warning(f"⚠️ Failed to save indexes to Storage (non-fatal): {save_err}")

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
        """
        Legacy function for query classification-based node retrieval.
        NOT used for mega-repos (which use hybrid retrieval instead).
        """
        try:
            # Safety guard: dependency_graph may be None for mega-repos
            if self.dependency_graph is None:
                logging.debug("dependency_graph is None (mega-repo), returning empty list")
                return []

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
        """
        Legacy function for relevance calculation.
        NOT used for mega-repos (which use hybrid retrieval instead).
        """
        try:
            node_embedding = self.vector_store.embeddings.embed_query(node)
            query_embedding = self.vector_store.embeddings.embed_query(query)
            similarity = cosine_similarity([node_embedding], [query_embedding])[0][0]

            # Safety guard: dependency_graph may be None for mega-repos
            if self.dependency_graph is not None:
                centrality = nx.pagerank(self.dependency_graph).get(node, 0)
            else:
                centrality = 0

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

    async def chat(self, query: str, node_contexts: List[dict] = None) -> str:
        """
        Chat with LLM using retrieved context (batch mode)

        NEW (Step 3): Uses Claude + reranking + smart context assembly
        OLD: Falls back to AI21 if Claude not available

        Args:
            query: User question
            node_contexts: Optional list of node contexts for multi-node queries (OPTION C extended)
        """
        try:
            # NEW: Use Claude if available (even without hybrid retriever)
            if self.claude_client:
                # If hybrid retriever available, use full pipeline
                if self.hybrid_retriever and self.reranker:
                    return await self._chat_with_claude(query, node_contexts=node_contexts)
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

        # Stream Claude response (filter out truncation markers)
        async for token in self._query_claude_stream(prompt):
            # Skip truncation markers (dict), only yield text tokens (str)
            if isinstance(token, dict):
                continue
            yield token

    async def _chat_with_claude(self, query: str, node_contexts: List[dict] = None) -> str:
        """
        NEW: Chat using Claude with full Step 1-3 pipeline

        Flow:
        1. Hybrid search (Step 2)
        2. Cross-encoder reranking (Step 3)
        3. Context assembly (Step 3)
        4. Claude LLM (Step 3)
        5. Citation extraction (Step 3)

        OPTION C: If node_contexts provided, force those chunks into results
        """
        if node_contexts and len(node_contexts) > 0:
            node_names = [nc.get('name') for nc in node_contexts]
            logging.info(f"Using Claude with MULTI-NODE retrieval for: {', '.join(node_names)}")
        else:
            logging.info("Using Claude with full retrieval pipeline (Steps 1-3)")

        # Detect query complexity and flow queries
        query_lower = query.lower()
        is_complex = any(word in query_lower for word in
                        ['complete', 'entire', 'all', 'flow', 'trace', 'execution', 'how does'])

        # FIX 4: Detect flow/trace queries specifically for deeper retrieval
        is_flow_query = any(phrase in query_lower for phrase in [
            'trace', 'flow', 'execution', 'call chain', 'step by step',
            'walk through', 'path from', 'sequence', 'what happens when',
            'creation flow', 'how is', 'how are', 'how does'
        ])

        # HCGS: Detect architectural/full-repo questions that benefit from hierarchical summaries
        is_architectural = any(phrase in query_lower for phrase in [
            'architecture', 'how does', 'interact', 'relationship', 'flow',
            'where do i', 'hook in', 'structure', 'overview', 'main component',
            'how are', 'what is the purpose', 'entry point', 'wire up'
        ])

        # FIX 4: Mega-repo guard for flow queries
        chunk_count = len(self.full_context) if isinstance(self.full_context, dict) else 0
        is_mega_repo = chunk_count > 50000

        # Calculate retrieval parameters based on query type and repo size
        if is_flow_query:
            if is_mega_repo:
                # Mega-repo: balance depth with performance
                flow_top_k = 40
                flow_expand_max = 60
                flow_expand_depth = 3
            else:
                # Normal repo: deeper traversal for complete call chains
                flow_top_k = 50
                flow_expand_max = 100
                flow_expand_depth = 4
            logging.info(f"🔍 Flow query detected: top_k={flow_top_k}, expand_max={flow_expand_max}, depth={flow_expand_depth}")
        else:
            flow_top_k = 20
            flow_expand_max = 30
            flow_expand_depth = 3

        logging.info(f"Query complexity: {'complex' if is_complex else 'simple'}, flow: {is_flow_query}, architectural: {is_architectural}")

        # SOTA UPGRADE (Jan 2026): Enhanced retrieval with query processing
        # Implements 3 research-backed techniques for +40-65% improvement

        # Detect codebase language distribution from chunks
        chunks_list = list(self.full_context.values()) if isinstance(self.full_context, dict) else []

        # Build language distribution for LLM-based intent detection
        # This gives the LLM context about what languages are available
        codebase_languages = {}
        for chunk in chunks_list[:500]:  # Sample first 500 for speed
            file_type = chunk.get('metadata', {}).get('file_type', 'unknown')
            # Normalize file extensions to language names
            lang_map = {
                'rs': 'rust', 'py': 'python', 'js': 'javascript', 'ts': 'typescript',
                'c': 'c', 'cpp': 'cpp', 'h': 'c', 'hpp': 'cpp', 'go': 'go',
                'java': 'java', 'php': 'php', 'rb': 'ruby', 'swift': 'swift',
                'kt': 'kotlin', 'scala': 'scala', 'jsx': 'javascript', 'tsx': 'typescript'
            }
            lang = lang_map.get(file_type, file_type)
            codebase_languages[lang] = codebase_languages.get(lang, 0) + 1

        # Get primary language (most files)
        codebase_language = max(codebase_languages.items(), key=lambda x: x[1])[0] if codebase_languages else "unknown"

        # SOTA (Jan 2026): LLM-based query intent language detection
        # Uses Claude Haiku to semantically understand what language the query is about
        # Research basis: "User intent understanding goes beyond keyword matching"
        # (Knowledge-Oriented RAG Survey, 2025)
        try:
            language = await detect_query_intent_language_llm(
                query=query,
                codebase_languages=codebase_languages,
                anthropic_client=self.claude_client,
                use_cache=True
            )
        except Exception as e:
            # Fallback to fast heuristic-based detection
            logging.warning(f"LLM intent detection failed: {e}, using heuristic fallback")
            language = detect_query_intent_language(query, codebase_language)

        logging.info(f"🌐 Codebase languages: {codebase_languages}")
        logging.info(f"🌐 Primary: {codebase_language} → Query intent: {language}")

        # Strategy 1: Query Expansion (+40% on vocabulary mismatch)
        # Expands query with code-specific terms to bridge semantic gap
        expanded_query = await expand_query_with_llm(query, language, self.claude_client)

        # Strategy 2: Query Decomposition (for complex queries)
        # Breaks complex queries into sub-queries for better coverage
        if is_complex:
            sub_queries = await decompose_query(query, self.claude_client)
            logging.info(f"🧩 Decomposed into {len(sub_queries)} sub-queries")

            # FIX 5: Parallelize sub-query processing for latency improvement
            # Each sub-query: expansion (~200ms) + retrieval (~300ms) = ~500ms
            # Serial: 3 queries × 500ms = 1.5s
            # Parallel: max(500ms) = ~500ms (3x faster)
            async def process_sub_query(sq: str, idx: int):
                """Process a single sub-query: expand + retrieve"""
                try:
                    logging.info(f"   Sub-query {idx}: '{sq}'")
                    sq_expanded = await expand_query_with_llm(sq, language, self.claude_client)
                    return self.hybrid_retriever.hybrid_search(
                        query=sq_expanded,
                        top_k=flow_top_k // len(sub_queries) + 5,  # Distribute across sub-queries
                        expand=True,
                        expand_max=flow_expand_max // len(sub_queries),
                        expand_depth=flow_expand_depth
                    )
                except Exception as e:
                    logging.warning(f"   Sub-query {idx} failed: {e}")
                    return []  # Graceful degradation

            # Execute sub-queries in parallel
            tasks = [process_sub_query(sq, i) for i, sq in enumerate(sub_queries, 1)]
            results = await asyncio.gather(*tasks)

            # Flatten results
            all_chunks_from_sub_queries = [chunk for result in results for chunk in result]

            # De-duplicate and take top chunks (use flow_top_k for flow queries)
            seen = set()
            deduped_chunks = []
            for chunk in all_chunks_from_sub_queries:
                if chunk['chunk_id'] not in seen:
                    seen.add(chunk['chunk_id'])
                    deduped_chunks.append(chunk)

            max_chunks = flow_top_k if is_flow_query else 50
            top_chunks = deduped_chunks[:max_chunks]
            logging.info(f"✅ Decomposition (parallel): Aggregated {len(all_chunks_from_sub_queries)} → {len(top_chunks)} unique chunks")

        else:
            # Strategy 3: Agentic Self-Reflection (for simple queries)
            # Self-correcting retrieval with query rewriting
            top_chunks = await agentic_retrieval_with_reflection(
                query=expanded_query,  # Use expanded query as base
                hybrid_retriever=self.hybrid_retriever,
                anthropic_client=self.claude_client,
                language=language,
                max_iterations=2,
                top_k=flow_top_k  # FIX 4: Use flow parameters
            )
            logging.info(f"✅ Agentic retrieval: {len(top_chunks)} chunks after self-reflection")

        if not top_chunks:
            return "I couldn't find relevant information in the codebase to answer your question."

        # OPTION C EXTENDED: Force selected nodes into context if provided
        if node_contexts and len(node_contexts) > 0:
            logging.info(f"🎯 MULTI-NODE CONTEXT: Forcing {len(node_contexts)} nodes into context")

            chunks_list = list(self.full_context.values()) if isinstance(self.full_context, dict) else []
            forced_chunks = []

            for i, node_ctx in enumerate(node_contexts, 1):
                target_chunk_id = node_ctx.get('chunk_id')
                node_type = node_ctx.get('type', 'unknown')
                node_name = node_ctx.get('name', target_chunk_id)

                logging.info(f"   Node {i}: {node_name} (type: {node_type})")

                # Handle file/directory nodes (get ALL chunks from file)
                if node_type in ['file', 'directory']:
                    file_chunks = [
                        c for c in chunks_list
                        if c.get('file_path') == target_chunk_id or
                           c.get('chunk_id', '').startswith(target_chunk_id + '::')
                    ]

                    if file_chunks:
                        # Prioritize by type
                        def chunk_priority(chunk):
                            type_priority = {'class_definition': 3, 'function': 2, 'method': 1}
                            return type_priority.get(chunk.get('type'), 0)

                        sorted_file_chunks = sorted(file_chunks, key=chunk_priority, reverse=True)

                        # Take top 10 per file (balanced for multi-file)
                        forced_chunks.extend(sorted_file_chunks[:10])
                        logging.info(f"      ✅ Added {len(sorted_file_chunks[:10])} chunks from {node_name}")
                    else:
                        logging.warning(f"      ⚠️ No chunks found for file: {target_chunk_id}")

                else:
                    # Handle method/function/class nodes (single chunk)
                    target_chunk = next((c for c in chunks_list if c.get('chunk_id') == target_chunk_id), None)

                    if target_chunk:
                        forced_chunks.append(target_chunk)
                        logging.info(f"      ✅ Added {node_name} chunk")
                    else:
                        logging.warning(f"      ⚠️ Could not find chunk: {target_chunk_id}")

            # Combine forced chunks + retrieval
            # Remove duplicates, keep forced chunks first
            forced_ids = {c['chunk_id'] for c in forced_chunks}
            retrieval_filtered = [c for c in top_chunks if c['chunk_id'] not in forced_ids]

            top_chunks = forced_chunks + retrieval_filtered[:5]
            logging.info(f"✅ Multi-node context: {len(forced_chunks)} forced + {len(retrieval_filtered[:5])} retrieved = {len(top_chunks)} total")

        logging.info(f"📊 SOTA retrieval returned {len(top_chunks)} chunks")

        # Step 2: Conditional cross-encoder reranking
        # - Complex/flow queries: Apply reranking for precision boost (+10-15%)
        # - Simple queries: Skip reranking (SOTA retrieval is already good)
        # This optimization reduces latency from 67s to 2-4s on CPU
        if is_complex or is_flow_query:
            rerank_k = 20 if is_flow_query else 15
            max_chunks = 15  # Limit chunks to rerank (diminishing returns after 15)
            reranked_chunks = self.reranker.rerank(
                query, top_chunks,
                top_k=rerank_k,
                max_chunks_to_rerank=max_chunks
            )
            logging.info(f"✅ Cross-encoder reranking: {len(top_chunks)} → {len(reranked_chunks)} chunks")
        else:
            # Simple queries: use SOTA ranking directly (faster)
            reranked_chunks = top_chunks[:15]
            logging.info(f"⚡ Skipped reranking for simple query (using SOTA ranking)")

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
        
        # HCGS: Add hierarchical summaries for architectural questions
        hcgs_context = ""
        if is_architectural and self.hierarchical_summaries:
            logging.info("📚 HCGS: Adding hierarchical summaries for architectural query")
            
            # Get relevant summaries based on query
            relevant_summaries = await retrieve_relevant_summaries(
                query, 
                self.hierarchical_summaries,
                self.claude_client,
                top_packages=10,
                top_files=20
            )
            
            # Build HCGS context
            hcgs_parts = []
            
            # Repository overview (always include for architectural questions)
            if relevant_summaries.get('repo'):
                hcgs_parts.append("## Repository Overview\n")
                hcgs_parts.append(relevant_summaries['repo'])
                hcgs_parts.append("\n")
            
            # Relevant package summaries
            if relevant_summaries.get('packages'):
                hcgs_parts.append("\n## Key Components\n")
                for pkg_path, pkg_summary in relevant_summaries['packages'][:10]:
                    hcgs_parts.append(f"**{pkg_path}**: {pkg_summary}\n")
            
            # Relevant file summaries
            if relevant_summaries.get('files'):
                hcgs_parts.append("\n## Relevant Files\n")
                for file_path, file_summary in relevant_summaries['files'][:15]:
                    hcgs_parts.append(f"- **{file_path}**: {file_summary}\n")
            
            hcgs_context = "\n".join(hcgs_parts)
            logging.info(f"📚 HCGS context: {len(hcgs_context)} chars added")

        context_text = hcgs_context + "\n" + "\n".join(assembled['context_parts'])
        logging.info(f"Assembled context: {assembled['chunks_included']} chunks, {assembled['total_tokens']} tokens + HCGS={len(hcgs_context)} chars")

        # Step 4: Build prompt for Claude
        prompt = self._build_claude_prompt(query, context_text, assembled, node_contexts)

        # Step 5: Query Claude
        response_text = await self._query_claude(prompt)

        # Step 6: Extract citations from response
        # For multi-node, pass first node for relative citation extraction (fallback)
        first_node_context = node_contexts[0] if node_contexts and len(node_contexts) > 0 else None
        citations = extract_citations_from_response(response_text, first_node_context)

        # Step 7: Map citations to chunk IDs for graph highlighting
        highlighted_nodes = []
        logging.info(f"🎯 HIGHLIGHTING DEBUG: Extracted {len(citations)} citations from Claude response")

        if citations:
            for i, cite in enumerate(citations, 1):
                logging.info(f"   Citation {i}: {cite}")

        if citations and self.repo_id:
            from backend.api.data_storage import map_citations_to_chunk_ids
            highlighted_nodes = map_citations_to_chunk_ids(citations, self.repo_id)
            logging.info(f"✅ Mapped {len(citations)} citations to {len(highlighted_nodes)} highlighted nodes")

            # =================================================================
            # MEGA-REPO FIX: Convert chunk IDs to file paths for graph matching
            # =================================================================
            # For mega-repos (>50K chunks), the graph shows file structure only
            # (directories + files), not individual functions/methods.
            #
            # Problem: highlighted_nodes are chunk IDs like "file.go::CreateServerChain"
            # but graph node IDs are file paths like "file.go"
            #
            # Solution: Convert chunk IDs to file paths for mega-repos
            # This ensures highlighted nodes match visible graph nodes
            # =================================================================
            MEGA_REPO_HIGHLIGHT_THRESHOLD = 50000  # Same as MEGA_REPO_THRESHOLD in initialize_hybrid_retriever

            # Check if this is a mega-repo by counting chunks in context
            chunk_count = len(self.full_context) if isinstance(self.full_context, dict) else 0

            if chunk_count > MEGA_REPO_HIGHLIGHT_THRESHOLD and highlighted_nodes:
                # Convert chunk IDs to file paths
                # Chunk ID format: "path/to/file.go::FunctionName" or "path/to/file.go"
                file_paths = []
                for chunk_id in highlighted_nodes:
                    # Extract file path (before :: if present)
                    if '::' in chunk_id:
                        file_path = chunk_id.split('::')[0]
                    else:
                        file_path = chunk_id

                    # Deduplicate while preserving order
                    if file_path not in file_paths:
                        file_paths.append(file_path)

                logging.info(f"🔄 MEGA-REPO: Converted {len(highlighted_nodes)} chunk IDs to {len(file_paths)} file paths for graph compatibility")
                logging.info(f"   File paths: {file_paths[:5]}{'...' if len(file_paths) > 5 else ''}")
                highlighted_nodes = file_paths

        elif not citations:
            logging.warning(f"⚠️ No citations found in Claude response - cannot highlight nodes")
        elif not self.repo_id:
            logging.warning(f"⚠️ No repo_id available - cannot map citations to chunks")

        # Step 8: Return structured response with highlighting data
        logging.info(f"📤 RESPONSE DEBUG: Returning structured response:")
        logging.info(f"   - Response text: {len(response_text)} chars")
        logging.info(f"   - Citations: {len(citations)}")
        logging.info(f"   - Highlighted nodes: {len(highlighted_nodes)}")
        if highlighted_nodes:
            logging.info(f"   - Node IDs: {highlighted_nodes}")

        return {
            'response': response_text,
            'citations': citations,
            'highlighted_nodes': highlighted_nodes
        }

    async def _chat_with_progress_stream(self, query: str, node_contexts: List[dict] = None):
        """
        SOTA: Chat with real-time progress streaming for interactive UX.

        Yields progress events at each pipeline stage with REAL values,
        then streams response tokens for typewriter effect.

        Event types:
        - intent: Query intent language detection
        - expand: Query expansion with terms
        - decompose: Query decomposition (complex queries)
        - search: Hybrid search results
        - rerank: Cross-encoder reranking
        - context: Context assembly
        - llm_start: Claude generation starting
        - token: Response token (streamed)
        - done: Complete with citations and highlights

        Args:
            query: User query
            node_contexts: Optional node contexts for per-node queries

        Yields:
            Dict with 'type' and event-specific data
        """
        import time
        start_time = time.time()

        # =====================================================================
        # STEP 0: Query Analysis
        # =====================================================================
        query_lower = query.lower()
        is_complex = any(word in query_lower for word in
                        ['complete', 'entire', 'all', 'flow', 'trace', 'execution', 'how does'])
        is_flow_query = any(phrase in query_lower for phrase in [
            'trace', 'flow', 'execution', 'call chain', 'step by step',
            'walk through', 'path from', 'sequence', 'what happens when',
            'creation flow', 'how is', 'how are', 'how does'
        ])
        is_architectural = any(phrase in query_lower for phrase in [
            'architecture', 'how does', 'interact', 'relationship', 'flow',
            'where do i', 'hook in', 'structure', 'overview', 'main component'
        ])

        chunk_count = len(self.full_context) if isinstance(self.full_context, dict) else 0
        is_mega_repo = chunk_count > 50000

        if is_flow_query:
            flow_top_k = 40 if is_mega_repo else 50
            flow_expand_max = 60 if is_mega_repo else 100
            flow_expand_depth = 3 if is_mega_repo else 4
        else:
            flow_top_k = 20
            flow_expand_max = 30
            flow_expand_depth = 3

        # =====================================================================
        # STEP 1: Query Intent Detection
        # =====================================================================
        chunks_list = list(self.full_context.values()) if isinstance(self.full_context, dict) else []

        codebase_languages = {}
        for chunk in chunks_list[:500]:
            file_type = chunk.get('metadata', {}).get('file_type', 'unknown')
            lang_map = {
                'rs': 'rust', 'py': 'python', 'js': 'javascript', 'ts': 'typescript',
                'c': 'c', 'cpp': 'cpp', 'go': 'go', 'java': 'java', 'jsx': 'javascript', 'tsx': 'typescript'
            }
            lang = lang_map.get(file_type, file_type)
            codebase_languages[lang] = codebase_languages.get(lang, 0) + 1

        codebase_language = max(codebase_languages.items(), key=lambda x: x[1])[0] if codebase_languages else "unknown"

        try:
            language = await detect_query_intent_language_llm(
                query=query,
                codebase_languages=codebase_languages,
                anthropic_client=self.claude_client,
                use_cache=True
            )
        except:
            language = detect_query_intent_language(query, codebase_language)

        yield {
            'type': 'intent',
            'message': f'Detected {language} query' + (f' (codebase is {codebase_language})' if language != codebase_language else ''),
            'language': language,
            'codebase_language': codebase_language,
            'elapsed_ms': int((time.time() - start_time) * 1000)
        }

        # =====================================================================
        # STEP 2: Query Expansion
        # =====================================================================
        expanded_query = await expand_query_with_llm(query, language, self.claude_client)

        # Extract expansion terms (difference between expanded and original)
        original_terms = set(query.lower().split())
        expanded_terms = [t for t in expanded_query.lower().split() if t not in original_terms][:8]

        yield {
            'type': 'expand',
            'message': f'Expanded with {len(expanded_terms)} technical terms',
            'terms': expanded_terms,
            'elapsed_ms': int((time.time() - start_time) * 1000)
        }

        # =====================================================================
        # STEP 3: Query Decomposition (complex queries only)
        # =====================================================================
        if is_complex:
            sub_queries = await decompose_query(query, self.claude_client)

            yield {
                'type': 'decompose',
                'message': f'Split into {len(sub_queries)} sub-queries',
                'sub_queries': sub_queries[:3],  # Show first 3
                'elapsed_ms': int((time.time() - start_time) * 1000)
            }

            # Process sub-queries in parallel
            async def process_sub_query(sq, idx):
                try:
                    sq_expanded = await expand_query_with_llm(sq, language, self.claude_client)
                    return self.hybrid_retriever.hybrid_search(
                        query=sq_expanded,
                        top_k=flow_top_k // len(sub_queries) + 5,
                        expand=True,
                        expand_max=flow_expand_max // len(sub_queries),
                        expand_depth=flow_expand_depth
                    )
                except:
                    return []

            tasks = [process_sub_query(sq, i) for i, sq in enumerate(sub_queries, 1)]
            results = await asyncio.gather(*tasks)

            all_chunks = [chunk for result in results for chunk in result]
            seen = set()
            deduped = []
            for chunk in all_chunks:
                if chunk['chunk_id'] not in seen:
                    seen.add(chunk['chunk_id'])
                    deduped.append(chunk)
            top_chunks = deduped[:flow_top_k]
        else:
            # Agentic retrieval with reflection
            top_chunks = await agentic_retrieval_with_reflection(
                query=expanded_query,
                hybrid_retriever=self.hybrid_retriever,
                anthropic_client=self.claude_client,
                language=language,
                max_iterations=2,
                top_k=flow_top_k
            )

        if not top_chunks:
            yield {
                'type': 'error',
                'message': "No relevant code found",
                'elapsed_ms': int((time.time() - start_time) * 1000)
            }
            return

        # =====================================================================
        # STEP 4: Search Results
        # =====================================================================
        # Get unique files from chunks
        files_found = list(set(c.get('file_path', '').split('/')[-1] for c in top_chunks if c.get('file_path')))[:5]

        yield {
            'type': 'search',
            'message': f'Found {len(top_chunks)} relevant chunks across {len(set(c.get("file_path") for c in top_chunks))} files',
            'chunk_count': len(top_chunks),
            'sample_files': files_found,
            'elapsed_ms': int((time.time() - start_time) * 1000)
        }

        # Handle node contexts (force selected nodes into context)
        if node_contexts and len(node_contexts) > 0:
            forced_chunks = []
            for node_ctx in node_contexts:
                target_id = node_ctx.get('chunk_id')
                node_type = node_ctx.get('type', 'unknown')

                if node_type in ['file', 'directory']:
                    file_chunks = [c for c in chunks_list
                                   if c.get('file_path') == target_id or
                                   c.get('chunk_id', '').startswith(target_id + '::')]
                    forced_chunks.extend(file_chunks[:10])
                else:
                    target = next((c for c in chunks_list if c.get('chunk_id') == target_id), None)
                    if target:
                        forced_chunks.append(target)

            forced_ids = {c['chunk_id'] for c in forced_chunks}
            retrieval_filtered = [c for c in top_chunks if c['chunk_id'] not in forced_ids]
            top_chunks = forced_chunks + retrieval_filtered[:5]

        # =====================================================================
        # STEP 5: Cross-encoder Reranking
        # =====================================================================
        if is_complex or is_flow_query:
            rerank_k = 20 if is_flow_query else 15
            reranked_chunks = self.reranker.rerank(query, top_chunks, top_k=rerank_k, max_chunks_to_rerank=15)

            # Get top file from reranking
            top_file = reranked_chunks[0].get('file_path', '').split('/')[-1] if reranked_chunks else None

            yield {
                'type': 'rerank',
                'message': f'Reranked to top {len(reranked_chunks)} most relevant chunks',
                'chunk_count': len(reranked_chunks),
                'top_file': top_file,
                'elapsed_ms': int((time.time() - start_time) * 1000)
            }
        else:
            reranked_chunks = top_chunks[:15]
            yield {
                'type': 'rerank',
                'message': f'Selected top {len(reranked_chunks)} chunks (simple query)',
                'chunk_count': len(reranked_chunks),
                'elapsed_ms': int((time.time() - start_time) * 1000)
            }

        # =====================================================================
        # STEP 6: Context Assembly
        # =====================================================================
        max_tokens = self._calculate_dynamic_token_budget(is_complex)
        avg_tokens_per_chunk = 500
        include_full = min(len(reranked_chunks), max_tokens // avg_tokens_per_chunk, 30)

        self.context_assembler.max_tokens = max_tokens
        assembled = self.context_assembler.assemble_context(reranked_chunks, include_full_code_top_n=include_full)

        # HCGS for architectural queries
        hcgs_context = ""
        if is_architectural and self.hierarchical_summaries:
            relevant_summaries = await retrieve_relevant_summaries(
                query, self.hierarchical_summaries, self.claude_client, top_packages=10, top_files=20
            )
            hcgs_parts = []
            if relevant_summaries.get('repo'):
                hcgs_parts.append("## Repository Overview\n" + relevant_summaries['repo'])
            if relevant_summaries.get('packages'):
                hcgs_parts.append("\n## Key Components\n")
                for pkg_path, pkg_summary in relevant_summaries['packages'][:10]:
                    hcgs_parts.append(f"**{pkg_path}**: {pkg_summary}\n")
            hcgs_context = "\n".join(hcgs_parts)

        context_text = hcgs_context + "\n" + "\n".join(assembled['context_parts'])

        yield {
            'type': 'context',
            'message': f'Assembled {assembled["total_tokens"]:,} tokens of context',
            'token_count': assembled['total_tokens'],
            'chunk_count': assembled['chunks_included'],
            'elapsed_ms': int((time.time() - start_time) * 1000)
        }

        # =====================================================================
        # STEP 7: Claude LLM Generation (Streaming)
        # =====================================================================
        yield {
            'type': 'llm_start',
            'message': 'Generating answer with Claude...',
            'elapsed_ms': int((time.time() - start_time) * 1000)
        }

        # Build prompt
        prompt = self._build_claude_prompt(query, context_text, assembled, node_contexts)

        # Stream response tokens
        response_text = ""
        was_truncated = False
        truncation_limit = None
        async for token in self._query_claude_stream(prompt):
            # Check for truncation marker (dict) vs actual token (str)
            if isinstance(token, dict) and token.get('_meta') == 'truncated':
                was_truncated = True
                truncation_limit = token.get('max_tokens')
                continue
            response_text += token
            yield {
                'type': 'token',
                'token': token
            }

        # Emit truncation warning if response was cut off
        if was_truncated:
            yield {
                'type': 'truncated',
                'message': f'Response was truncated at {truncation_limit:,} tokens',
                'max_tokens': truncation_limit,
                'elapsed_ms': int((time.time() - start_time) * 1000)
            }

        # =====================================================================
        # STEP 8: Citation Extraction & Completion
        # =====================================================================
        first_node_context = node_contexts[0] if node_contexts and len(node_contexts) > 0 else None
        citations = extract_citations_from_response(response_text, first_node_context)

        highlighted_nodes = []
        if citations and self.repo_id:
            from backend.api.data_storage import map_citations_to_chunk_ids
            highlighted_nodes = map_citations_to_chunk_ids(citations, self.repo_id)

            # Mega-repo: convert chunk IDs to file paths
            if chunk_count > 50000 and highlighted_nodes:
                file_paths = []
                for chunk_id in highlighted_nodes:
                    file_path = chunk_id.split('::')[0] if '::' in chunk_id else chunk_id
                    if file_path not in file_paths:
                        file_paths.append(file_path)
                highlighted_nodes = file_paths

        yield {
            'type': 'done',
            'message': 'Complete',
            'citations': citations,
            'highlighted_nodes': highlighted_nodes,
            'total_elapsed_ms': int((time.time() - start_time) * 1000)
        }

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

    def _build_claude_prompt(self, query: str, context_text: str, assembled: Dict, node_contexts: List[dict] = None) -> Dict[str, str]:
        """
        Build structured prompt for Claude with caching support

        Args:
            query: User query
            context_text: Assembled context
            assembled: Assembly metadata
            node_contexts: Optional node contexts for focused queries

        Returns:
            Dict with 'system_and_context' (cacheable) and 'query_part' (not cacheable)
        """
        # Get conversation history
        history_messages = self.memory.load_memory_variables({})
        history = history_messages.get('history', [])

        # Part 1: System instructions + Code context (CACHEABLE - rarely changes per repo)
        system_and_context = f"""You are an expert software engineer analyzing a codebase. Your role is to help developers understand the code by providing clear, accurate, and insightful explanations.

RELEVANT CODE CONTEXT:
{context_text}
"""

        # Part 2: Conversation history + Query + Instructions (NOT CACHEABLE - changes every query)
        query_part = ""

        # Add conversation history if exists
        if history:
            query_part += "CONVERSATION HISTORY:\n"
            for msg in history[-4:]:  # Last 4 messages
                role = "User" if hasattr(msg, 'type') and msg.type == "human" else "Assistant"
                content = msg.content if hasattr(msg, 'content') else str(msg)
                query_part += f"{role}: {content}\n"
            query_part += "\n"

        # Default: not a flow query (will be set to True if detected below)
        is_flow_query = False

        # Add node-focused instructions if this is a per-node/multi-node query
        if node_contexts and len(node_contexts) > 0:
            if len(node_contexts) == 1:
                # Single node - focused query
                node_ctx = node_contexts[0]
                query_part += f"""IMPORTANT CONTEXT:
The user clicked on {node_ctx['name']} ({node_ctx['type']}) and is asking specifically about this code.
Focus your answer EXCLUSIVELY on {node_ctx['name']}. Other code in the context is for reference only.

USER QUESTION:
{query}

INSTRUCTIONS:
1. Answer specifically about {node_ctx['name']} - this is what the user clicked
2. Always cite code using this exact format: {node_ctx['name']}:25-35 (include the filename in every citation, even though focusing on one file)
3. Only mention other code if it directly relates to {node_ctx['name']}
4. Be concise and focused on this specific code entity
5. Use a confident, knowledgeable tone

Your answer:"""
            else:
                # Multi-node - relationship query
                node_names = [nc['name'] for nc in node_contexts]
                node_list = ', '.join(node_names)

                query_part += f"""IMPORTANT CONTEXT:
The user selected {len(node_contexts)} files/nodes: {node_list}
They want to understand how these specific code entities relate to each other.
Focus your answer EXCLUSIVELY on these {len(node_contexts)} selected items and their interactions.

USER QUESTION:
{query}

INSTRUCTIONS:
1. Explain the relationships and interactions between: {node_list}
2. Cite code using format: filename:25-35 for each reference
3. Focus on data flow, function calls, and dependencies between these specific files
4. Ignore code outside these {len(node_contexts)} selected items unless directly relevant
5. Be concise and show how these pieces connect

Your answer:"""
        else:
            # Detect flow/trace queries for specialized instructions
            is_flow_query = any(word in query.lower() for word in
                ['trace', 'flow', 'execution', 'call chain', 'step by step',
                 'how does', 'walk through', 'path from', 'sequence', 'what happens when'])

            if is_flow_query:
                query_part += f"""USER QUESTION:
{query}

EXECUTION FLOW TRACING INSTRUCTIONS:
1. Trace the COMPLETE execution path from entry point to final destination
2. Show EVERY intermediate function/method in the call chain as numbered steps
3. For each step include: function name, file:line, and key logic (2-3 lines)
4. **ALWAYS include actual code snippets** in triple backticks with language identifier
5. Format as: 1. Entry → 2. Handler → 3. Business logic → 4. Data layer
6. Reference files with line numbers: `filename.php:42-68`
7. Show data transformations at each step when relevant

Example format:
**Step 1: Entry Point** - `WallPresenter.php:267`
```php
public function renderMakePost(): void {{
    $this->assertUserLoggedIn();
```

**Step 2: Validation** - `WallPresenter.php:280`
...

Your answer:"""
            else:
                query_part += f"""USER QUESTION:
{query}

INSTRUCTIONS:
1. Answer based on the provided code context above
2. **ALWAYS include actual code snippets** in triple backticks with language identifier
3. Reference specific files and line numbers when discussing code (format: file.py:42-68)
4. For "how does X work" questions: Show the actual implementation code
5. If the context doesn't contain enough information, say so clearly
6. Be concise but thorough - show code, don't just describe it
7. Use a confident, knowledgeable tone (like a senior engineer explaining to a teammate)

Your answer:"""

        return {
            'system_and_context': system_and_context,
            'query_part': query_part,
            'is_flow_query': is_flow_query  # Used to set max_tokens in _query_claude
        }

    async def _query_claude(self, prompt_parts: Dict[str, str]) -> str:
        """
        Query Claude 4.0 Sonnet (batch mode) with prompt caching

        Args:
            prompt_parts: Dict with 'system_and_context' (cacheable), 'query_part' (not cacheable),
                         and 'is_flow_query' (bool for token limit)

        Returns:
            Claude's response
        """
        try:
            # Use Claude 4.0 Sonnet with prompt caching
            # Cache system + context (1,129-6,642 tokens) for 90% cost savings
            # Flow queries need more tokens for detailed step-by-step traces
            # Claude Sonnet 4 supports up to 64k output tokens - we use 16k for flow, 4k for normal
            is_flow_query = prompt_parts.get('is_flow_query', False)
            max_tokens = 16000 if is_flow_query else 4000
            logging.info(f"🎯 Claude max_tokens={max_tokens} (is_flow_query={is_flow_query})")

            response = self.claude_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                temperature=0.3,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt_parts['system_and_context'],
                                "cache_control": {"type": "ephemeral"}  # Cache for 5 min (default)
                            },
                            {
                                "type": "text",
                                "text": prompt_parts['query_part']
                            }
                        ]
                    }
                ]
            )

            # Extract text from response
            response_text = response.content[0].text

            # Reconstruct full prompt for memory (backwards compat)
            full_prompt = prompt_parts['system_and_context'] + "\n" + prompt_parts['query_part']

            # Save to conversation memory
            self.memory.save_context(
                {"input": full_prompt},
                {"output": response_text}
            )

            # Log cache usage for monitoring
            usage = response.usage
            if hasattr(usage, 'cache_read_input_tokens') and usage.cache_read_input_tokens > 0:
                logging.info(f"💰 CACHE HIT: {usage.cache_read_input_tokens} tokens read from cache (90% savings)")
            elif hasattr(usage, 'cache_creation_input_tokens') and usage.cache_creation_input_tokens > 0:
                logging.info(f"📝 CACHE WRITE: {usage.cache_creation_input_tokens} tokens cached for future queries")

            return response_text

        except Exception as e:
            logging.error(f"Error querying Claude: {e}")
            raise

    async def _query_claude_stream(self, prompt_parts: Dict[str, str]):
        """
        Query Claude 4.0 Sonnet (streaming mode) with prompt caching

        Streams tokens as they're generated for better perceived latency.
        Uses same caching strategy as batch mode.

        Args:
            prompt_parts: Dict with 'system_and_context' (cacheable), 'query_part' (not cacheable),
                         and 'is_flow_query' (bool for token limit)

        Yields:
            Token chunks (str) from Claude, then optionally a truncation marker (dict)
            at the end if response was cut off at max_tokens limit.

            Truncation marker format: {'_meta': 'truncated', 'max_tokens': <limit>}
        """
        try:
            # Use Claude 4.0 Sonnet with streaming + caching
            # Flow queries need more tokens for detailed step-by-step traces
            # Claude Sonnet 4 supports up to 64k output tokens - we use 16k for flow, 4k for normal
            is_flow_query = prompt_parts.get('is_flow_query', False)
            max_tokens = 16000 if is_flow_query else 4000
            logging.info(f"🎯 Claude stream max_tokens={max_tokens} (is_flow_query={is_flow_query})")

            full_response = ""
            was_truncated = False

            with self.claude_client.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                temperature=0.3,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt_parts['system_and_context'],
                                "cache_control": {"type": "ephemeral"}
                            },
                            {
                                "type": "text",
                                "text": prompt_parts['query_part']
                            }
                        ]
                    }
                ]
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    yield text

                # Check if response was truncated at token limit
                final_message = stream.get_final_message()
                if final_message.stop_reason == "max_tokens":
                    was_truncated = True
                    logging.warning(f"⚠️ Response truncated at {max_tokens} tokens (stop_reason=max_tokens)")

            # Reconstruct full prompt for memory
            full_prompt = prompt_parts['system_and_context'] + "\n" + prompt_parts['query_part']

            # Save complete response to conversation memory
            self.memory.save_context(
                {"input": full_prompt},
                {"output": full_response}
            )

            # Yield truncation marker at the end if response was cut off
            if was_truncated:
                yield {'_meta': 'truncated', 'max_tokens': max_tokens}

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

        # Update repo_id (in case session was cached from different repo)
        if repo_id and chat_session.repo_id != repo_id:
            logging.debug(f"Updating cached session repo_id: {chat_session.repo_id} → {repo_id}")
            chat_session.repo_id = repo_id

        # Stream the response
        async for token in chat_session.chat_stream(query):
            yield token

    except Exception as e:
        logging.error(f"Error in streaming response: {e}")
        yield f"Error: {str(e)}"


async def get_jamba_response_progress_stream(
    query: str,
    context: Dict[str, Any],
    repo_id: int = None,
    node_contexts: List[dict] = None
):
    """
    SOTA: Streaming query with real-time progress events.

    Yields progress events at each pipeline stage with REAL values,
    then streams response tokens for typewriter effect.

    This is used by /api/query_stream for interactive "agent thinking" UX.

    Event types:
    - intent: Query intent language detection
    - expand: Query expansion with terms
    - decompose: Query decomposition (complex queries)
    - search: Hybrid search results
    - rerank: Cross-encoder reranking
    - context: Context assembly
    - llm_start: Claude generation starting
    - token: Response token (streamed)
    - done: Complete with citations and highlights

    Args:
        query: User query
        context: Code context
        repo_id: Repository ID
        node_contexts: Optional node contexts for per-node queries

    Yields:
        Dict with 'type' and event-specific data
    """
    try:
        logging.info(f"🚀 Progress stream query: {query[:50]}...")

        # Build session (same as batch)
        context_string = json.dumps(context, sort_keys=True)
        session_id = hashlib.md5(context_string.encode()).hexdigest()

        if session_id not in chat_sessions:
            chat_sessions[session_id] = ChatSession(repo_id=repo_id)
            await chat_sessions[session_id].initialize_conversation_chain(context)

        chat_session = chat_sessions[session_id]

        # Update repo_id if needed
        if repo_id and chat_session.repo_id != repo_id:
            chat_session.repo_id = repo_id

        # Check if hybrid retriever and reranker available
        if not chat_session.claude_client or not chat_session.hybrid_retriever or not chat_session.reranker:
            # Fallback to non-streaming response
            response = await chat_session.chat(query, node_contexts=node_contexts)
            yield {'type': 'token', 'token': response}
            yield {'type': 'done', 'message': 'Complete', 'citations': [], 'highlighted_nodes': []}
            return

        # Stream progress events
        async for event in chat_session._chat_with_progress_stream(query, node_contexts=node_contexts):
            yield event

    except IndexingInProgressError as e:
        yield {'type': 'error', 'message': str(e), 'indexing_in_progress': True}
    except Exception as e:
        logging.error(f"Error in progress stream: {e}", exc_info=True)
        yield {'type': 'error', 'message': f"Error: {str(e)}"}


async def get_jamba_response(query: str, context: Dict[str, Any], repo_id: int = None, node_contexts: List[dict] = None) -> str:
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
            new_session = ChatSession(repo_id=repo_id)
            try:
                # Convert context to chunk format if it's chunks from DB
                # For Step 1: context is still file-level from frontend
                # Vector store will handle both formats
                await new_session.initialize_conversation_chain(context)
                # Only cache session if initialization succeeded
                chat_sessions[session_id] = new_session
            except IndexingInProgressError:
                # Don't cache broken session - let next query retry properly
                logging.info(f"Session not cached - indexing still in progress (repo_id={repo_id})")
                raise

        chat_session = chat_sessions[session_id]

        # Update repo_id (in case session was cached from different repo)
        if repo_id and chat_session.repo_id != repo_id:
            logging.debug(f"Updating cached session repo_id: {chat_session.repo_id} → {repo_id}")
            chat_session.repo_id = repo_id

        # OPTION C: Pass node_contexts through to chat
        response = await chat_session.chat(query, node_contexts=node_contexts)
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
