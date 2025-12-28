#!/bin/bash
# Script to pre-render graph positions for a mega repo locally
# Usage: ./scripts/prerender_graph_local.sh kubernetes/kubernetes

REPO_NAME=${1:-"kubernetes/kubernetes"}

echo "🚀 Pre-rendering graph positions for: $REPO_NAME"
echo "=============================================="
echo ""
echo "This will:"
echo "1. Open your browser to the local frontend"
echo "2. You manually upload: https://github.com/$REPO_NAME"
echo "3. Let ForceAtlas2 stabilize (30-60 min for mega repos)"
echo "4. Positions auto-save to Supabase"
echo ""
echo "⚠️  Make sure your frontend and backend are running first:"
echo "   Terminal 1: cd frontend && npm run dev"
echo "   Terminal 2: cd backend && uvicorn main:app --reload"
echo ""

# Check if frontend is running
if ! curl -s http://localhost:5173 > /dev/null 2>&1; then
    echo "❌ Frontend not running on localhost:5173"
    echo "   Run: cd frontend && npm run dev"
    exit 1
fi

# Check if backend is running
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "⚠️  Backend might not be running on localhost:8000"
    echo "   Run: cd backend && uvicorn main:app --reload"
fi

echo "✅ Frontend detected. Opening browser..."
echo ""
echo "📋 INSTRUCTIONS:"
echo "   1. Browser will open to localhost:5173"
echo "   2. Paste this URL: https://github.com/$REPO_NAME"
echo "   3. Click upload"
echo "   4. Wait for graph to stabilize (watch the loading indicator)"
echo "   5. Once stable, positions auto-save to Supabase"
echo ""

# Open browser based on OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "http://localhost:5173"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    xdg-open "http://localhost:5173"
else
    echo "Open http://localhost:5173 in your browser"
fi

echo "⏳ Let the graph stabilize. This window can be closed."
echo "   The browser will handle everything automatically."

