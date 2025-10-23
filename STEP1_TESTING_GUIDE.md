# STEP 1 TESTING GUIDE

## What Was Changed

### Database
- ✅ Added `chunks` table to store function/class-level code chunks
- ✅ Added indexes for performance
- ✅ Added functions: `store_chunks_batch()`, `retrieve_chunks()`, `get_chunk_by_id()`
- ✅ **CRITICAL FIX:** `initialize_database()` now called on server startup

### Code Processing
- ✅ New module: `chunk_processor.py` - converts AST to semantic chunks
- ✅ Chunks respect function/class boundaries (not arbitrary line splits)
- ✅ Each chunk has metadata: type, name, file, lines, imports

### Upload Flow
- ✅ `main.py` now processes repo into chunks during upload
- ✅ Chunks stored in database
- ✅ Stats logged: "Generated N chunks from M files"

### Vector Store (Embeddings)
- ✅ Switched from AI21Embeddings to OpenAIEmbeddings
- ✅ Vector store can handle chunk-level documents
- ✅ Backward compatible with old file-level context

### New Dependencies
- ✅ Added `langchain-openai` and `openai` to requirements.txt

## Environment Setup

1. **Install new dependencies:**
   ```bash
   pip install langchain-openai openai
   ```

2. **Create `.env` file:**
   ```bash
   cp .env.example .env
   ```

3. **Add your OpenAI API key to `.env`:**
   ```
   OPENAI_API_KEY=sk-...your-key-here...
   GITHUB_AUTH_TOKEN=ghp_...your-token...
   AI21_API_KEY=...your-ai21-key...
   ```

4. **Delete old database (fresh start):**
   ```bash
   rm data_storage.db
   ```

## Running Tests

### Unit Tests (Chunking Logic)
```bash
python -m pytest backend/tests/test_chunk_processor.py -v
```

**Expected:** 14/14 tests passing

### Integration Tests (Full Flow)
```bash
python -m pytest backend/tests/test_step1_integration.py -v -s
```

**Expected:** 3/3 tests passing, should print:
```
✅ Integration test passed!
   - Created repo_id: 1
   - Generated 3 chunks
   - Function chunks: 2
   - Class chunks: 1
```

## Manual Testing (Local Server)

### 1. Start the backend server:
```bash
cd /Users/shreshth.rajan/projects/visdep
python -m backend.main
```

**Expected output:**
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 2. Upload a test repository:

Use this small test repo:
```
https://github.com/octocat/Hello-World
```

Make API call:
```bash
curl -X POST http://localhost:8000/api/upload_repo \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/octocat/Hello-World"}'
```

**Expected response:**
```json
{
  "message": "Repository data successfully uploaded, parsed, and graph generated.",
  "chunks": 5,
  "files_processed": 3
}
```

**Check logs for:**
```
INFO: Generated 5 chunks from 3 files
INFO: Chunk types: {'function': 3, 'file': 2}
INFO: Chunks stored in database
INFO: Using new chunk-level context format
INFO: Creating FAISS index with 5 documents
```

### 3. Verify chunks in database:

```bash
sqlite3 data_storage.db "SELECT chunk_id, type, name FROM chunks;"
```

**Expected output:**
```
README::file_content::L1|file|README
index.html::file_content::L1|file|index.html
...
```

### 4. Query the new chunks endpoint:

```bash
curl http://localhost:8000/api/chunks/1 | python -m json.tool
```

**Expected:** JSON object with chunk_ids as keys, each chunk containing:
- chunk_id
- file_path
- type (function/class/file)
- name
- code
- start_line, end_line
- metadata

### 5. Test the chat with chunks:

**Start frontend:**
```bash
cd frontend
npm start
```

**Upload a repo through UI, then ask:**
```
"What functions are in this repository?"
```

**Expected behavior:**
- Chat should respond with specific function names
- Response should cite files (not just general info)

## What Should Work

✅ **Database migration:** New `chunks` table created automatically
✅ **Repo upload:** Chunks generated and stored
✅ **Chunk retrieval:** `/api/chunks/{repo_id}` returns chunk data
✅ **Vector store:** Uses OpenAI embeddings on chunks
✅ **Backward compat:** Old context.json still works

## What Changed (Breaking)

❌ **NONE** - This is fully backward compatible!

- Old file-level context still works
- New chunk-level context is additive
- Vector store handles both formats

## Known Limitations (Step 1)

1. **Function extraction is heuristic-based**
   - Works well for Python, JS, Java
   - May miss edge cases (nested functions, weird indentation)
   - Will be fixed with tree-sitter in future

2. **Still using file-level context in `/api/context`**
   - Frontend still fetches context.json
   - New `/api/chunks/{repo_id}` endpoint available but not used yet
   - Will update frontend in future

3. **OpenAI embeddings are general-purpose**
   - Good baseline but not code-specific
   - Will upgrade to Qodo/Nomic in Step 2

4. **No graph-based retrieval yet**
   - Just vector similarity search
   - Graph expansion comes in Step 2

## Success Criteria

✅ All 17 unit tests passing (14 + 3 integration)
✅ Database migration completes without errors
✅ Repo upload generates chunks (visible in logs)
✅ Chunks stored in database (verifiable via sqlite3)
✅ Vector store created with OpenAI embeddings
✅ Chat still works (backward compatible)

## If Something Breaks

### Issue: "AI21_API_KEY not set"
**Fix:** Add AI21_API_KEY to `.env` (still needed for Step 1)

### Issue: "OPENAI_API_KEY not set"
**Fix:** Add OPENAI_API_KEY to `.env`
```bash
export OPENAI_API_KEY=sk-...
```

### Issue: "No module named 'langchain_openai'"
**Fix:** Install dependencies
```bash
pip install langchain-openai openai
```

### Issue: Database errors
**Fix:** Delete and recreate database
```bash
rm data_storage.db
python -m backend.main  # Will recreate on startup
```

### Issue: Chunks not generated
**Check logs for:**
- "Processing repository into chunks..."
- "Generated N chunks from M files"

If missing, the AST parsing failed. Check file content is not empty.

## Next Steps

After Step 1 is validated:

**Step 2:** Graph-guided hybrid retrieval
- Add BM25 keyword search
- Implement graph expansion
- Multi-factor ranking

**Step 3:** Cross-encoder reranking + context assembly
- Rerank chunks
- Switch to Claude
- Add citations

## Questions?

If anything doesn't work as expected, check:
1. All dependencies installed
2. Environment variables set
3. Database initialized (data_storage.db exists)
4. Logs show chunk processing
5. Tests pass

**All tests should be GREEN before proceeding to Step 2.**
