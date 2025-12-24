# Debugging Guide - Multi-Repo Issues

## 🔍 COMPREHENSIVE LOGGING ADDED:

### **Frontend Console Logs:**

**Repo Switching:**
```
🔄 LOAD REPO FROM HISTORY: {repoName, localRepoId, repoId}
✅ Activate endpoint called
✅ Cleared old highlights
✅ currentRepo set, will trigger graph refetch
📡 FETCH GRAPH: {currentRepoId: 42}
📡 Fetching from: /api/dependency_graph?repo_id=42
✅ Graph received: {nodes: 792, firstNode: "..."}
```

**Session Restore:**
```
💬 LOAD SESSION: {sessionId, title, messages: 5, contextNodes: 2, highlights: 3}
✅ Chat history set
✅ Context nodes set
✅ Highlighted nodes set - should trigger canvas update
🔵 HIGHLIGHT UPDATE TRIGGERED: {hasNetwork: true, hasGraphData: true, highlightCount: 3}
🔄 Updating 792 total nodes, 3 to highlight
✅ Canvas updated: 3 cyan, 789 normal
```

**Canvas Highlighting:**
```
🔵 HIGHLIGHT UPDATE TRIGGERED: {...}
⏭️ Skipping: Network not ready (if fails early)
🔄 Updating X nodes, Y to highlight
✅ Canvas updated: Y cyan, X-Y normal
❌ Canvas update error: ... (if fails)
```

---

## 🐛 DEBUGGING ISSUES:

### **Issue 1: Repo Switching Doesn't Load Graph**

**Check console for:**
```
📡 FETCH GRAPH: {currentRepoId: 42}
📡 Fetching from: /api/dependency_graph?repo_id=42
```

**If currentRepoId is undefined:**
- currentRepo state not set correctly
- Check: onLoadRepo sets setCurrentRepo(repo)

**If graph doesn't load:**
- Check backend logs: "📊 Loading graph for repo_id=42"
- Check if file exists: dependency_graph_42.json
- May need to re-upload repo

### **Issue 2: Highlights Don't Appear**

**Check console for:**
```
✅ Highlighted nodes set - should trigger canvas update
🔵 HIGHLIGHT UPDATE TRIGGERED: {highlightCount: 3}
```

**If triggered but no update:**
```
⏭️ Skipping: Network not ready
```
- Graph not loaded yet
- Try after graph stabilizes

**If updates but nodes not cyan:**
```
✅ Canvas updated: 3 cyan
```
- Updates succeeded
- Nodes might be off-screen
- Try zooming out or using search

### **Issue 3: Drag-Drop Broken**

**Check console for:**
```
🎯 Drag started: filename
✅ Dropped on chat area
```

**If ghost doesn't appear:**
- onNodeDragStart not firing
- Check vis-network dragStart event

**If drop doesn't work:**
- Check position calculation
- Right 384px of screen = chat area

---

## 🔧 BACKEND LOGGING:

**Graph Loading:**
```
📊 Loading graph for repo_id=42
```

**If file not found:**
```
FileNotFoundError: dependency_graph_42.json
```
- Repo needs to be re-uploaded
- Or file was deleted

**Global State:**
```
✅ Activated repo 42 (global state updated)
```

**If activate fails:**
- Check sys.modules['__main__'] works
- May need different approach

---

## ✅ VERIFICATION STEPS:

**Test Repo Switch:**
1. Upload 2 repos
2. Open console (F12)
3. Click History → Click first repo
4. Watch for: "📡 Fetching from: /api/dependency_graph?repo_id=X"
5. Should see: "✅ Graph received: {nodes: ...}"

**Test Session Restore:**
1. Create chat with query
2. Create new chat
3. Click Chats → Click first chat
4. Watch for: "🔵 HIGHLIGHT UPDATE TRIGGERED"
5. Should see: "✅ Canvas updated: N cyan"

**Test Highlighting:**
1. Query
2. See cyan nodes
3. Click FOCUS
4. Click ✕ FOCUS
5. Watch console - highlights should persist

---

**All logs prefixed with emojis for easy scanning in console.**
