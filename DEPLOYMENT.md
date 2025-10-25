# 🚀 PRODUCTION DEPLOYMENT GUIDE

## **Prerequisites**
- ✅ Railway account (done)
- ✅ Vercel account (done)
- ✅ Domain: visdep.com (done)

---

## **STEP 1: RAILWAY BACKEND DEPLOYMENT**

### **1.1 Create Persistent Volume**
1. Go to Railway project: https://railway.com/project/1b503db1-167c-4ce5-9fe1-0e3ef2fb7e2c
2. Click on your service
3. Go to **Settings → Volumes**
4. Click **"Add Volume"**
5. Set mount path: `/data`
6. Size: 1 GB (sufficient for MVP)
7. Click **"Add"**

### **1.2 Set Environment Variables**
In Railway → Settings → Variables, add:

```
GITHUB_AUTH_TOKEN=ghp_your_token
OPENAI_API_KEY=sk-your_key
ANTHROPIC_API_KEY=sk-ant-api03-your_key
DATABASE_PATH=/data/data_storage.db
FAISS_DIR=/data/faiss_indexes
ALLOWED_ORIGINS=https://visdep.com,https://www.visdep.com,https://visdep.vercel.app
PORT=8000
```

### **1.3 Deploy**
1. Railway will auto-deploy from GitHub (already connected)
2. Wait for build to complete (~3-5 minutes)
3. Get deployment URL: `https://visdep-production.up.railway.app` (or similar)
4. **Test:** Visit `https://your-url.railway.app/api/dependency_graph`
5. **Expected:** `{"nodes": [], "edges": []}` (empty but working!)

---

## **STEP 2: VERCEL FRONTEND DEPLOYMENT**

### **2.1 Install Vercel CLI (if not done)**
```bash
npm install -g vercel
```

### **2.2 Deploy Frontend**
```bash
cd frontend
vercel --prod
```

**Or via Vercel Dashboard:**
1. Go to vercel.com/shreshthrajan
2. Click "New Project"
3. Import from GitHub: select visdep repo
4. Root Directory: `frontend`
5. Framework: Create React App (auto-detected)
6. Click "Deploy"

### **2.3 Set Environment Variable**
In Vercel → Project Settings → Environment Variables:

```
REACT_APP_API_URL=https://your-railway-url.up.railway.app
```

**Redeploy** after adding env var.

---

## **STEP 3: DOMAIN CONFIGURATION**

### **3.1 Point Domain to Vercel**
In Squarespace DNS settings:

**A Record:**
```
Host: @
Points to: 76.76.21.21 (Vercel IP)
```

**CNAME Record:**
```
Host: www
Points to: cname.vercel-dns.com
```

### **3.2 Add Domain in Vercel**
1. Vercel → Project → Settings → Domains
2. Add domain: `visdep.com`
3. Add domain: `www.visdep.com`
4. Wait for DNS propagation (5-60 minutes)

---

## **STEP 4: VERIFICATION**

### **4.1 Backend Health Check**
```bash
curl https://your-railway-url.railway.app/api/dependency_graph
```
**Expected:** `{"nodes": [], "edges": []}`

### **4.2 Frontend Check**
Visit: `https://visdep.com`
**Expected:** Home page loads ✅

### **4.3 End-to-End Test**
1. Visit visdep.com
2. Upload gpt-engineer repo
3. Ask: "How does authentication work?"
4. **Expected:** Answer with citations ✅

---

## **TROUBLESHOOTING**

### **Railway Build Fails:**
- Check logs in Railway dashboard
- Common issue: Missing dependencies in requirements.txt
- Solution: Verify all packages listed

### **Frontend Can't Connect to Backend:**
- Check `REACT_APP_API_URL` set correctly
- Check CORS allows your domain
- Check Railway service is running

### **Database Errors:**
- Verify volume mounted at `/data`
- Check DATABASE_PATH=/data/data_storage.db
- SSH into Railway: `railway shell` → `ls /data`

---

## **ARCHITECTURE**

```
User → visdep.com (Vercel)
         ↓
     Frontend (React)
         ↓ API calls
     Backend (Railway)
         ↓ Reads/Writes
     SQLite on /data volume (Railway)
     FAISS indexes on /data volume (Railway)
```

---

## **POST-DEPLOYMENT**

### **Monitor:**
- Railway dashboard: CPU, memory, requests
- Vercel analytics: Page views, performance
- Error tracking: Check Railway logs

### **Scaling:**
If you hit limits:
- Add more Railway replicas (requires Postgres migration)
- Increase volume size
- Optimize queries further

---

## **ESTIMATED COSTS**

| Service | Plan | Cost |
|---------|------|------|
| Railway | Hobby ($5) + Volume ($1/GB) | ~$6/month |
| Vercel | Hobby (Free) | $0 |
| Supabase | Not used yet | $0 |
| **Total** | | **~$6/month** |

---

## **SUCCESS CRITERIA**

✅ visdep.com loads frontend
✅ Can upload repository
✅ Can query and get answers
✅ Answers have citations
✅ Cache works (repeat queries instant)
✅ No errors in logs

**Once all checked: You're in production!** 🚀
