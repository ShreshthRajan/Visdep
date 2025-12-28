#!/bin/bash
# Run pre-indexing for all mega repos
# This will take DAYS to complete (each repo is 5-15 hours + 30-60 min for positions)

echo "🚀 PRE-INDEXING ALL MEGA REPOS"
echo "=========================================="
echo ""
echo "This will process 20 mega repos:"
echo "  - Each repo: 5-15 hours (chunks, indexes, summaries)"
echo "  - Each repo: 30-60 min (graph positions via Playwright)"
echo "  - Total time: ~5-10 DAYS if run sequentially"
echo ""
echo "⚠️  RECOMMENDATION: Run this on a server/VPS, not your laptop"
echo ""

# Check which repos are already done
echo "📊 Checking existing repos..."
python3 -c "
import os, sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()
from backend.api.supabase_client import get_supabase_client
supabase = get_supabase_client()
result = supabase.table('preindexed_repos').select('repo_name').execute()
done = {r['repo_name'] for r in (result.data or [])}
print(f'Already done: {len(done)} repos')
for repo in done:
    print(f'  ✅ {repo}')
"

echo ""
read -p "Continue with pre-indexing? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Run pre-indexing for all repos
echo ""
echo "🚀 Starting pre-indexing (this will take DAYS)..."
echo "   You can Ctrl+C and resume later - completed repos are saved"
echo ""

./venv/bin/python scripts/preindex_mega_repos.py --all

echo ""
echo "✅ Pre-indexing complete!"
echo "   Check results above for any failures"

