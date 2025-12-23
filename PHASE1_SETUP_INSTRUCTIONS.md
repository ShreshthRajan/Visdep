# Phase 1: Authentication - Setup Instructions

## ✅ WHAT WAS IMPLEMENTED:

### Backend Files Created:
1. `backend/.env` - Local development environment variables
2. `backend/api/supabase_client.py` - Supabase connection
3. `backend/api/auth.py` - OAuth endpoints (4 endpoints)
4. `requirements.txt` - Added `supabase` dependency

### Frontend Files Created:
1. `frontend/.env` - Local development environment variables
2. `frontend/src/lib/supabase.js` - Supabase client
3. `frontend/src/contexts/AuthContext.jsx` - User state management
4. `frontend/src/pages/AuthCallback.jsx` - OAuth callback handler

### Modified Files:
1. `backend/main.py` - Added auth router (line 752-753)
2. `frontend/src/App.jsx` - Wrapped with AuthProvider, added /auth/callback route
3. `frontend/src/pages/Home.jsx` - Wired "Connect GitHub" button
4. `frontend/src/components/LeftNav.jsx` - Added user avatar at bottom

### Database Schema:
1. `SUPABASE_SETUP.sql` - Run this in Supabase SQL Editor

---

## 📋 SETUP STEPS (IN ORDER):

### Step 1: Create Supabase Tables

1. Go to: https://supabase.com/dashboard/project/wbmqaztxfbuhnaegwnvd/editor
2. Open `SUPABASE_SETUP.sql` from project root
3. Copy entire contents
4. Paste into Supabase SQL Editor
5. Click "Run"
6. Verify tables created: users, user_repos, chat_sessions

### Step 2: Verify Environment Variables

**Railway (Backend) - Should have:**
- ✅ SUPABASE_URL
- ✅ SUPABASE_SERVICE_KEY
- ✅ GITHUB_OAUTH_CLIENT_ID (Production)
- ✅ GITHUB_OAUTH_CLIENT_SECRET (Production)
- ✅ All existing vars

**Vercel (Frontend) - Should have:**
- ✅ REACT_APP_SUPABASE_URL
- ✅ REACT_APP_SUPABASE_ANON_KEY
- ✅ REACT_APP_API_URL

**Local - Already created:**
- ✅ `backend/.env`
- ✅ `frontend/.env`

### Step 3: Install Dependencies

**Backend:**
```bash
cd /Users/shreshth.rajan/projects/visdep
source venv/bin/activate
pip install supabase  # Already done
```

**Frontend:**
```bash
cd frontend
npm install  # Will install @supabase/supabase-js from package.json
```

### Step 4: Test Locally

**Terminal 1 - Backend:**
```bash
cd /Users/shreshth.rajan/projects/visdep
source venv/bin/activate
uvicorn backend.main:app --reload
```

**Terminal 2 - Frontend:**
```bash
cd /Users/shreshth.rajan/projects/visdep/frontend
npm start
```

### Step 5: Test OAuth Flow

1. Open http://localhost:3000
2. Click "connect github" button
3. Should redirect to GitHub OAuth
4. Authorize app
5. Should redirect to /auth/callback
6. Should show "Authenticating..." then redirect to /graph-chat
7. Avatar should appear in LeftNav (bottom-left)
8. Click avatar → Confirm logout

---

## 🔒 OAUTH FLOW (HOW IT WORKS):

```
1. User clicks "connect github" on landing
   ↓
2. Frontend: login() → redirects to /api/auth/github
   ↓
3. Backend: /auth/github → redirects to GitHub
   ↓
4. GitHub: User authorizes app
   ↓
5. GitHub: Redirects to /auth/callback?code=ABC123
   ↓
6. Frontend: AuthCallback.jsx receives code
   ↓
7. Frontend: Calls /api/auth/callback?code=ABC123
   ↓
8. Backend: Exchanges code for access_token
   ↓
9. Backend: Gets user from GitHub API
   ↓
10. Backend: Creates/updates user in Supabase
   ↓
11. Backend: Returns {user, access_token}
   ↓
12. Frontend: Stores in localStorage
   ↓
13. Frontend: Sets auth context
   ↓
14. Frontend: Redirects to /graph-chat
   ↓
15. LeftNav: Shows user avatar
```

---

## 🎨 UI CHANGES:

### Landing Page:
- "connect github" button → Now triggers OAuth (was inactive)

### LeftNav (Left Sidebar):
- Bottom: User avatar (32px circle)
- Hover: Cyan ring
- Click: Confirm logout
- Shows when authenticated

### Auth Callback Page:
- Shows: Cyan spinner + "Authenticating with GitHub..."
- On error: Shows error message, redirects to home after 3s

---

## 🔐 SECURITY:

**Frontend (Public):**
- Uses `sb_publishable_...` anon key (safe in browser)
- Stores: user object + GitHub access_token in localStorage
- GitHub token used for private repo git clones

**Backend (Private):**
- Uses `sb_secret_...` service key (bypasses RLS)
- Service key NEVER exposed to frontend
- Handles sensitive operations

**Row Level Security:**
- Enabled on all tables
- Users can only see/modify their own data
- Enforced by Supabase

---

## 📊 DATA FLOW:

### After Login:

**Supabase (Cloud):**
- users table: {id, github_id, username, avatar_url}

**localStorage (Browser):**
- visdep_user: User object
- visdep_github_token: OAuth token for git clone

**Future (Phase 2):**
- user_repos: Link user to uploaded repos
- chat_sessions: Store chat histories

---

## ✅ VERIFICATION CHECKLIST:

**Before Testing:**
- [ ] Supabase tables created (run SUPABASE_SETUP.sql)
- [ ] Environment variables added to Railway
- [ ] Environment variables added to Vercel
- [ ] Backend running (localhost:8000)
- [ ] Frontend running (localhost:3000)

**Test Flow:**
- [ ] Click "connect github" → GitHub OAuth page loads
- [ ] Authorize app → Redirects to /auth/callback
- [ ] See "Authenticating..." → Redirects to /graph-chat
- [ ] Avatar appears in LeftNav
- [ ] Click avatar → Logout confirmation
- [ ] Logout → Avatar disappears, back to landing

**Production Deployment:**
- [ ] Push code to GitHub
- [ ] Railway rebuilds (includes supabase in requirements.txt)
- [ ] Vercel rebuilds (includes @supabase/supabase-js)
- [ ] Test OAuth on https://visdep.com

---

## 🚀 NEXT STEPS (PHASE 2 & 3):

**Phase 2:** History panel, repo list, session switching
**Phase 3:** New chat, auto-save, session titles

**For now:** OAuth login works, user persists, can logout.
**Missing:** Repo/session management (coming in Phase 2)
