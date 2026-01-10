# Visdep Security & Stability Fix Plan

**Ground Truth Analysis** - Every issue verified by reading source code line-by-line.

---

## CORRECTION: API Keys Are NOT in Git

Upon verification:
- `.env` is properly in `.gitignore` (line 100)
- `git rev-list --all -- .env` returns 0 commits
- `.env` has NEVER been committed

**Initial audit was incorrect.** This is NOT a blocker.

---

## Verified Critical Issues

### 1. Authorization Bypass in Session Endpoints (CRITICAL)
**File:** `backend/api/sessions.py`
**Lines:** 67-92, 124-155, 158-172

**Problem:** `get_session`, `update_session`, and `delete_session` accept any session_id without verifying the requesting user owns that session.

```python
# Line 67-92: Anyone can read any session by ID
@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    result = supabase.table('chat_sessions')\
        .select('*')\
        .eq('id', session_id)\  # No user_id check!
        .single()\
        .execute()
```

**Impact:** Any authenticated user can read, modify, or delete any other user's chat sessions if they can guess/enumerate session IDs (UUIDs are not secret).

**Fix:**
```python
@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user_id: str):
    result = supabase.table('chat_sessions')\
        .select('*')\
        .eq('id', session_id)\
        .eq('user_id', user_id)\  # ADD THIS
        .single()\
        .execute()
```

Apply same pattern to `update_session` and `delete_session`.

---

### 2. OAuth CSRF Vulnerability (CRITICAL)
**File:** `backend/api/auth.py`
**Lines:** 32-53, 56-136

**Problem:** OAuth flow has no `state` parameter for CSRF protection.

```python
# Line 44-50: No state parameter generated
github_auth_url = (
    f"https://github.com/login/oauth/authorize"
    f"?client_id={GITHUB_CLIENT_ID}"
    f"&redirect_uri={CALLBACK_URL}"
    f"&scope=user:email repo"
    # Missing: &state={random_token}
)
```

**Impact:** Attackers can initiate OAuth flows that log victims into attacker-controlled accounts (session fixation).

**Fix:**
```python
import secrets

@router.get("/auth/github")
async def github_oauth_redirect(response: Response):
    state = secrets.token_urlsafe(32)
    # Store state in cookie with short TTL
    response.set_cookie("oauth_state", state, max_age=600, httponly=True, samesite="lax")

    github_auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={CALLBACK_URL}"
        f"&scope=user:email repo"
        f"&state={state}"
    )
    return RedirectResponse(github_auth_url)

@router.get("/auth/callback")
async def github_oauth_callback(code: str, state: str, request: Request):
    stored_state = request.cookies.get("oauth_state")
    if not stored_state or state != stored_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    # ... rest of callback
```

---

### 3. GitHub Token in localStorage (HIGH - XSS Risk)
**File:** `frontend/src/contexts/AuthContext.jsx`
**Lines:** 63-65

**Problem:** GitHub OAuth token stored in localStorage, accessible to any JavaScript.

```javascript
// Line 64-65
localStorage.setItem('visdep_user', JSON.stringify(userData));
localStorage.setItem('visdep_github_token', token);
```

**Impact:** Any XSS vulnerability allows token theft and full account compromise.

**Fix:** Use httpOnly cookies for token storage (requires backend changes):

1. Backend sets httpOnly cookie on OAuth callback
2. Frontend sends credentials with requests (`credentials: 'include'`)
3. Remove localStorage token storage

**Alternative (faster to implement):** If XSS is unlikely (no user-generated HTML), document the risk and add CSP headers:
```
Content-Security-Policy: default-src 'self'; script-src 'self'
```

---

### 4. Date.prototype Pollution (MEDIUM)
**Files:**
- `frontend/src/components/ChatHistoryPanel.jsx` lines 234-241
- `frontend/src/components/HistoryPanel.jsx` lines 215-223

**Problem:** Both files add `toRelativeTime()` to `Date.prototype` globally.

```javascript
// Line 234-241 ChatHistoryPanel.jsx
Date.prototype.toRelativeTime = function() {
  const seconds = Math.floor((new Date() - this) / 1000);
  // ...
};
```

**Impact:** Can break third-party libraries that use Date prototype, pollutes global namespace.

**Fix:** Create utility function instead:

```javascript
// utils/dateUtils.js
export function toRelativeTime(date) {
  const seconds = Math.floor((new Date() - date) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 2592000) return `${Math.floor(seconds / 86400)}d ago`;
  return `${Math.floor(seconds / 2592000)}mo ago`;
}

// Usage:
import { toRelativeTime } from '../utils/dateUtils';
// ...
{toRelativeTime(new Date(session.updated_at))}
```

---

### 5. Unbounded Memory Cache (MEDIUM)
**File:** `backend/api/data_storage.py`
**Line:** 17

**Problem:** `_chunks_cache = {}` grows indefinitely with no eviction.

```python
# Line 17
_chunks_cache = {}

# Line 349: Keeps adding entries
_chunks_cache[repo_id] = chunks
```

**Impact:** Server will OOM after processing many repos.

**Fix:** Use LRU cache with max size:

```python
from functools import lru_cache
from collections import OrderedDict

class LRUCache(OrderedDict):
    def __init__(self, maxsize=100):
        super().__init__()
        self.maxsize = maxsize

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self.maxsize:
            oldest = next(iter(self))
            del self[oldest]

_chunks_cache = LRUCache(maxsize=50)  # Keep 50 most recent repos
```

---

### 6. Supabase Client Created with Undefined Values (MEDIUM)
**File:** `frontend/src/lib/supabase.js`
**Lines:** 12-20

**Problem:** Logs error but continues to create client with undefined values.

```javascript
// Lines 15-18: Logs error but doesn't stop
if (!supabaseUrl || !supabaseAnonKey) {
  console.error('❌ Missing Supabase environment variables')
  // Client is still created below with undefined values!
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {...})
```

**Impact:** Cryptic runtime errors instead of clear startup failure.

**Fix:**
```javascript
if (!supabaseUrl || !supabaseAnonKey) {
  console.error('❌ Missing Supabase environment variables')
  throw new Error('Missing required Supabase configuration. Set REACT_APP_SUPABASE_URL and REACT_APP_SUPABASE_ANON_KEY')
}
```

---

### 7. Dockerfile Copies .env.example as .env (LOW)
**File:** `Dockerfile`
**Line:** 22

**Problem:** Overwrites any .env file with example values.

```dockerfile
COPY .env.example .env
```

**Impact:** In Docker builds, production env vars set via `docker run -e` may be ignored if app reads from .env file.

**Fix:** Remove this line. Use environment variables directly:
```dockerfile
# REMOVE: COPY .env.example .env
```

---

### 8. Conflicting Deployment Configs (LOW)
**Files:** `railway.json` and `railway.toml`

**Problem:** Two configs with different builders:
- `railway.json`: NIXPACKS builder
- `railway.toml`: DOCKERFILE builder

**Impact:** Confusion, potential deployment issues.

**Fix:** Keep only `railway.toml` (DOCKERFILE), delete `railway.json`.

---

### 9. No Version Pinning in requirements.txt (LOW)
**File:** `requirements.txt`

**Problem:** Only playwright has version pin. All other deps unpinned.

**Impact:** Non-reproducible builds, potential breakage from upstream changes.

**Fix:** Pin all versions:
```bash
pip freeze > requirements.txt
```

Or at minimum pin major versions:
```
fastapi>=0.100.0,<1.0.0
uvicorn>=0.23.0,<1.0.0
# etc.
```

---

## Non-Issues (Verified False Positives)

### Global State Race Condition
**File:** `backend/main.py` line 42

**Status:** MOSTLY FIXED

All critical endpoints now require explicit `repo_id`:
- `/api/dependency_graph` - line 1103: `if not repo_id: raise HTTPException(400, ...)`
- `/api/query` - line 1248: `if not request.repo_id: raise HTTPException(400, ...)`
- `/api/query_stream` - line 1367: `if not request.repo_id: ...`

Only `/api/context` (line 1677) uses global fallback - this is a legacy endpoint that should be deprecated.

**Action:** Add deprecation warning to `/api/context`, plan removal.

---

## Implementation Priority

| Priority | Issue | Effort | Risk if Not Fixed |
|----------|-------|--------|-------------------|
| P0 | Session auth bypass | 1 hour | Users can read other users' chats |
| P0 | OAuth CSRF | 2 hours | Account hijacking |
| P1 | Token in localStorage | 4 hours | Full account compromise on XSS |
| P2 | Date.prototype pollution | 30 min | Library conflicts |
| P2 | Unbounded cache | 1 hour | Server OOM |
| P2 | Supabase undefined | 15 min | Cryptic errors |
| P3 | Dockerfile .env | 5 min | Build issues |
| P3 | Conflicting configs | 5 min | Confusion |
| P3 | Version pinning | 30 min | Reproducibility |

**Total estimated: ~9 hours for all fixes**

---

## Recommended Fix Order

1. **Session auth bypass** - Simple parameter addition
2. **OAuth CSRF** - Add state parameter
3. **Supabase undefined** - Quick throw statement
4. **Date.prototype** - Extract to utility
5. **Dockerfile** - Remove one line
6. **Conflicting configs** - Delete railway.json
7. **Unbounded cache** - Add LRU
8. **Version pinning** - pip freeze
9. **Token storage** - More complex, can defer

---

## Verification After Fixes

1. **Session auth:** Try to GET `/sessions/{other_user_session_id}` without matching user_id - should 403/404
2. **OAuth CSRF:** Start OAuth, modify state param in callback URL - should reject
3. **Supabase:** Remove env vars, restart app - should throw clear error
4. **Date.prototype:** Verify no global pollution with `Object.keys(Date.prototype)`
5. **Cache:** Load 60 repos, verify only 50 in cache
6. **Docker:** Build and verify env vars work correctly

---

## Launch Recommendation

**Can launch after P0 fixes (2-3 hours):**
- Session auth bypass
- OAuth CSRF

**Should fix before scaling:**
- Unbounded cache (will OOM with growth)
- Token storage (if expecting any user-generated content)

**Confidence: 8/10** (was 3/10 before re-analysis)

The API keys issue was a false alarm - .env is not in git. The remaining issues are real but fixable in hours, not weeks.
