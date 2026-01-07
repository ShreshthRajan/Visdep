// frontend/src/pages/graphchat.jsx
import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import DependencyGraph from '../components/DependencyGraph';
import Chatbot from '../components/Chatbot';
import LeftNav from '../components/LeftNav';
import NodeInspector from '../components/NodeInspector';
import HistoryPanel from '../components/HistoryPanel';
import ChatHistoryPanel from '../components/ChatHistoryPanel';
import API from '../api';

const GraphChat = () => {
  const [highlightedNodes, setHighlightedNodes] = useState([]);
  const [inspectedNode, setInspectedNode] = useState(null);  // Currently previewing in inspector
  const [selectedNodes, setSelectedNodes] = useState([]);  // Context for queries
  const [activeTab, setActiveTab] = useState('chat');
  const [draggedNode, setDraggedNode] = useState(null);  // Currently dragging node
  const [showHistory, setShowHistory] = useState(false);  // Phase 2: Repo history panel
  const [showChats, setShowChats] = useState(false);  // Phase 3: Chat history panel

  // Resizable chat panel
  const [chatPanelWidth, setChatPanelWidth] = useState(384);  // Default w-96 = 384px
  const [isResizing, setIsResizing] = useState(false);
  const resizeRef = useRef(null);

  // Phase 3: Session management
  const [currentRepo, setCurrentRepo] = useState(null);  // Current repo metadata from Supabase
  const [currentSession, setCurrentSession] = useState(null);  // Current chat session
  const { user } = useAuth();

  // Ref to track selectedNodes without causing re-renders
  const selectedNodesRef = useRef([]);

  // Shared chat state
  const [chatHistory, setChatHistory] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [progressSteps, setProgressSteps] = useState([]);

  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Sync ref with state (no re-render, just tracking)
  useEffect(() => {
    selectedNodesRef.current = selectedNodes;
  }, [selectedNodes]);

  // Resizable panel handlers
  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isResizing) return;

      // Calculate new width based on mouse position from right edge
      const newWidth = window.innerWidth - e.clientX;

      // Clamp between min (320px) and max (800px)
      const clampedWidth = Math.min(Math.max(newWidth, 320), 800);
      setChatPanelWidth(clampedWidth);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      document.body.style.cursor = 'default';
      document.body.style.userSelect = 'auto';
    };

    if (isResizing) {
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing]);

  // Phase 3: Initialize currentRepo from URL params (primary) or sessionStorage (fallback)
  // URL params are reliable across all browsers; sessionStorage may fail on Chrome/Safari (quota)
  useEffect(() => {
    if (currentRepo) return; // Already initialized

    const urlRepoId = searchParams.get('repo_id');

    // PRIMARY: Read from URL params (works on all browsers)
    if (urlRepoId) {
      // Create minimal repo object with local_repo_id for DependencyGraph
      // Full repo metadata will be fetched from API if needed for sessions
      setCurrentRepo({ local_repo_id: urlRepoId, id: null, repo_name: 'Loading...' });
      console.log('✅ Initialized currentRepo from URL:', urlRepoId);

      // Fetch full repo metadata from API (async, non-blocking)
      if (user) {
        API.get(`/api/user/${user.id}/repos`).then(response => {
          const repos = response.data;
          const matchedRepo = repos?.find(r => r.local_repo_id === urlRepoId);
          if (matchedRepo) {
            setCurrentRepo(matchedRepo);
            console.log('✅ Loaded full repo metadata:', matchedRepo.repo_name);
          }
        }).catch(err => {
          console.warn('⚠️ Could not fetch repo metadata:', err.message);
          // Non-fatal: graph still works with local_repo_id
        });
      }
      return;
    }

    // FALLBACK: Read from sessionStorage (may fail on Chrome/Safari with large repos)
    try {
      const storedRepo = sessionStorage.getItem('visdep_current_repo');
      if (storedRepo) {
        const repo = JSON.parse(storedRepo);
        setCurrentRepo(repo);
        sessionStorage.removeItem('visdep_current_repo');
        console.log('✅ Initialized currentRepo from sessionStorage:', repo.repo_name);
      }
    } catch (err) {
      console.warn('⚠️ sessionStorage read failed:', err.message);
    }
  }, [currentRepo, searchParams, user]);

  // Phase 3: Auto-create first session when repo is loaded
  useEffect(() => {
    const initSession = async () => {
      if (!currentRepo || !user || currentSession) return;

      try {
        // Check if any sessions exist for this repo
        const sessionsResponse = await API.get(`/api/user/${user.id}/repo/${currentRepo.id}/sessions`);
        const sessions = sessionsResponse.data;

        if (sessions && sessions.length > 0) {
          // Load most recent session
          const mostRecent = sessions[0];
          setCurrentSession(mostRecent);
          setChatHistory(mostRecent.messages || []);
          setSelectedNodes(mostRecent.context_nodes || []);
          setHighlightedNodes(mostRecent.highlighted_nodes || []);
          console.log('✅ Loaded existing session');
        } else {
          // No sessions exist, create first one
          const response = await API.post('/api/sessions', {
            user_id: user.id,
            user_repo_id: currentRepo.id
          });
          setCurrentSession(response.data.session);
          console.log('✅ Auto-created first session');
        }
      } catch (err) {
        console.error('⚠️ Session initialization failed:', err);
      }
    };

    initSession();
  }, [currentRepo, user]);

  const handleHighlightNodes = useCallback((nodeIds) => {
    setHighlightedNodes(nodeIds || []);
  }, []);

  const handleNodeSelect = useCallback((node, event) => {
    if (!node) {
      // Clicking empty space - preserve context, just deselect visually
      return;
    }

    // Multi-select with Cmd/Ctrl+click - adds directly to context
    if (event && (event.metaKey || event.ctrlKey)) {
      setSelectedNodes(prev => {
        // Toggle: remove if already selected, add if not
        const isSelected = prev.some(n => n.id === node.id);
        if (isSelected) {
          return prev.filter(n => n.id !== node.id);
        } else {
          return [...prev, node];
        }
      });
      // Clear inspector preview when using multi-select
      setInspectedNode(null);
    } else {
      // Regular click - preview in inspector (don't add to context yet)
      setInspectedNode(node);

      // Only open inspector if no context exists (using ref to avoid re-render)
      if (selectedNodesRef.current.length === 0) {
        setActiveTab('inspector');
      }
      // Otherwise stay in current tab (user is building multi-node context)
    }
  }, []);

  // Main query handler with REAL SSE progress streaming
  // Replaces hardcoded fake progress with real-time updates from the retrieval pipeline
  const handleSubmitQuery = useCallback(async (queryText, nodeContext = null) => {
    if (!queryText.trim() || isLoading) return;

    const newMessage = { type: 'user', text: queryText };
    setChatHistory(prev => [...prev, newMessage]);
    setIsLoading(true);

    // Use selectedNodes if no explicit nodeContext provided
    const contextNodes = nodeContext ? [nodeContext] : selectedNodes;

    // Initialize progress with "Starting..." - will be replaced by real events
    setProgressSteps([{ id: 0, message: 'Starting query...', status: 'active' }]);

    // Build request payload
    const payload = {
      query: queryText,
      repo_id: currentRepo?.local_repo_id
    };

    if (contextNodes.length > 0) {
      payload.node_contexts = contextNodes.map(node => ({
        chunk_id: node.id,
        name: node.label?.split('\n')[0] || node.id,
        type: node.type
      }));
    }

    let responseText = '';
    let highlightedNodes = [];
    let stepId = 0;

    try {
      // Use SSE streaming for real-time progress
      const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiUrl}/api/query_stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error(`Query failed: ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      // Read SSE stream
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Split by SSE delimiter (double newline)
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;

          try {
            const event = JSON.parse(line.slice(6));

            switch (event.type) {
              case 'intent':
                stepId++;
                setProgressSteps([{
                  id: stepId,
                  message: event.message,
                  status: 'active',
                  detail: event.language !== event.codebase_language ? `${event.language} (cross-language)` : null
                }]);
                break;

              case 'expand':
                stepId++;
                setProgressSteps(prev => [
                  ...prev.map(s => ({ ...s, status: 'complete' })),
                  {
                    id: stepId,
                    message: event.message,
                    status: 'active',
                    detail: event.terms?.slice(0, 4).join(', ')
                  }
                ]);
                break;

              case 'decompose':
                stepId++;
                setProgressSteps(prev => [
                  ...prev.map(s => ({ ...s, status: 'complete' })),
                  {
                    id: stepId,
                    message: event.message,
                    status: 'active',
                    detail: event.sub_queries?.[0]?.substring(0, 40)
                  }
                ]);
                break;

              case 'search':
                stepId++;
                setProgressSteps(prev => [
                  ...prev.map(s => ({ ...s, status: 'complete' })),
                  {
                    id: stepId,
                    message: event.message,
                    status: 'active',
                    detail: event.sample_files?.slice(0, 3).join(', ')
                  }
                ]);
                break;

              case 'rerank':
                stepId++;
                setProgressSteps(prev => [
                  ...prev.map(s => ({ ...s, status: 'complete' })),
                  {
                    id: stepId,
                    message: event.message,
                    status: 'active',
                    detail: event.top_file ? `Top: ${event.top_file}` : null
                  }
                ]);
                break;

              case 'context':
                stepId++;
                setProgressSteps(prev => [
                  ...prev.map(s => ({ ...s, status: 'complete' })),
                  {
                    id: stepId,
                    message: event.message,
                    status: 'active',
                    detail: `${event.chunk_count} chunks`
                  }
                ]);
                break;

              case 'llm_start':
                stepId++;
                setProgressSteps(prev => [
                  ...prev.map(s => ({ ...s, status: 'complete' })),
                  {
                    id: stepId,
                    message: event.message,
                    status: 'active'
                  }
                ]);
                break;

              case 'token':
                // Accumulate response tokens (typewriter effect in Chatbot)
                responseText += event.token;
                // Update the last message in chat history with streaming response
                setChatHistory(prev => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (lastIdx >= 0 && updated[lastIdx].type === 'bot' && updated[lastIdx].streaming) {
                    updated[lastIdx] = { type: 'bot', text: responseText, streaming: true };
                  } else {
                    updated.push({ type: 'bot', text: responseText, streaming: true });
                  }
                  return updated;
                });
                break;

              case 'truncated':
                // Response was cut off at token limit - add warning
                stepId++;
                setProgressSteps(prev => [
                  ...prev.map(s => ({ ...s, status: 'complete' })),
                  {
                    id: stepId,
                    message: event.message,
                    status: 'error',  // Show as warning/error
                    detail: 'Response may be incomplete'
                  }
                ]);
                // Append truncation notice to response
                responseText += '\n\n---\n*⚠️ Response was truncated due to length limit. Try a more specific query for complete results.*';
                setChatHistory(prev => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (lastIdx >= 0 && updated[lastIdx].streaming) {
                    updated[lastIdx] = { type: 'bot', text: responseText, streaming: true };
                  }
                  return updated;
                });
                break;

              case 'done':
                // Mark all steps complete
                setProgressSteps(prev => prev.map(s => ({ ...s, status: 'complete' })));
                highlightedNodes = event.highlighted_nodes || [];

                // Finalize the response (remove streaming flag)
                setChatHistory(prev => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (lastIdx >= 0 && updated[lastIdx].streaming) {
                    updated[lastIdx] = { type: 'bot', text: responseText };
                  }
                  return updated;
                });

                if (highlightedNodes.length > 0) {
                  handleHighlightNodes(highlightedNodes);
                }
                break;

              case 'error':
                setProgressSteps([{ id: 999, message: event.message, status: 'error' }]);
                setChatHistory(prev => [...prev, { type: 'bot', text: event.message }]);
                break;

              default:
                console.log('Unknown event type:', event.type);
            }
          } catch (e) {
            console.error('Error parsing SSE event:', e);
          }
        }
      }

      // Auto-save session after query
      if (currentSession && user && responseText) {
        const botMessage = { type: 'bot', text: responseText };
        const updatedMessages = [...chatHistory, newMessage, botMessage];
        const sessionTitle = currentSession.title || queryText.substring(0, 50);

        setTimeout(async () => {
          try {
            await API.put(`/api/sessions/${currentSession.id}`, {
              messages: updatedMessages,
              context_nodes: selectedNodes.map(n => ({
                chunk_id: n.id,
                name: n.label?.split('\n')[0],
                type: n.type
              })),
              highlighted_nodes: highlightedNodes,
              title: sessionTitle
            });
            console.log('💾 Session auto-saved');
          } catch (err) {
            console.error('⚠️ Auto-save failed:', err);
          }
        }, 500);
      }

    } catch (error) {
      console.error('Query error:', error);
      let errorMessage = 'Error querying Visdep';
      if (error.message) {
        errorMessage = error.message;
      }
      setChatHistory(prev => [...prev, { type: 'bot', text: errorMessage }]);
    } finally {
      setIsLoading(false);
      setProgressSteps([]);
    }
  }, [isLoading, handleHighlightNodes, selectedNodes, currentRepo, currentSession, user, chatHistory]);

  const handleExplain = useCallback(async (node) => {
    setActiveTab('chat');
    const name = node.label?.split('\n')[0] || node.id;
    await handleSubmitQuery(`Explain what ${name} does`, node);
  }, [handleSubmitQuery]);

  const handleAskQuestion = useCallback((node) => {
    // Move inspected node to context
    setSelectedNodes(prev => {
      // If node already in context, don't duplicate
      const isAlreadySelected = prev.some(n => n.id === node.id);
      if (isAlreadySelected) {
        return prev;
      }
      return [...prev, node];
    });
    setInspectedNode(null);  // Clear inspector preview
    setActiveTab('chat');
  }, []);

  const handleClearContext = useCallback(() => {
    setSelectedNodes([]);
  }, []);

  const handleRemoveNode = useCallback((index) => {
    setSelectedNodes(prev => prev.filter((_, i) => i !== index));
  }, []);

  const handleNewChat = useCallback(async () => {
    if (!user || !currentRepo) return;

    try {
      // Create new session in Supabase
      const response = await API.post('/api/sessions', {
        user_id: user.id,
        user_repo_id: currentRepo.id
      });

      const newSession = response.data.session;

      // Clear current chat
      setChatHistory([]);
      setSelectedNodes([]);
      setInspectedNode(null);
      setHighlightedNodes([]);  // FIX: Clear graph highlights from previous chat

      // Set new session as current
      setCurrentSession(newSession);

      console.log('✅ New chat created:', newSession.id);
    } catch (err) {
      console.error('❌ Error creating new chat:', err);
    }
  }, [user, currentRepo, chatHistory]);

  const handleAddNodeToContext = useCallback((node) => {
    // Add node to context if not already present
    setSelectedNodes(prev => {
      const isAlreadySelected = prev.some(n => n.id === node.id);
      if (isAlreadySelected) {
        return prev;  // Don't add duplicates
      }
      return [...prev, node];
    });
    setActiveTab('chat');  // Switch to chat tab
  }, []);

  const handleNodeDragStart = useCallback(({ node, ghostElement }) => {
    let rafId = null;

    // Track mouse movement with RAF throttle (60fps smooth)
    const handleMouseMove = (e) => {
      if (rafId) return;  // Skip if RAF already scheduled

      rafId = requestAnimationFrame(() => {
        if (ghostElement) {
          ghostElement.style.left = (e.clientX + 10) + 'px';
          ghostElement.style.top = (e.clientY + 10) + 'px';
        }
        rafId = null;
      });
    };

    // Detect mouse release anywhere (even outside canvas)
    const handleMouseUp = (e) => {
      // Check if dropped over chat area (right 384px)
      const windowWidth = window.innerWidth;
      const chatAreaLeft = windowWidth - 384;
      const isOverChat = e.clientX >= chatAreaLeft;

      if (isOverChat) {
        console.log('✅ Dropped on chat area, adding to context');
        handleAddNodeToContext(node);
      } else {
        console.log('❌ Dropped outside chat area');
      }

      // Cleanup: Remove ghost and listeners
      if (ghostElement && ghostElement.parentNode) {
        ghostElement.remove();
      }
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      if (rafId) {
        cancelAnimationFrame(rafId);
      }

      setDraggedNode(null);
    };

    // Attach global listeners
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    // Store node for indicator
    setDraggedNode(node);
  }, [handleAddNodeToContext]);

  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ backgroundColor: '#050505' }}>
      {/* Full-bleed graph canvas */}
      <div className="absolute inset-0">
        <DependencyGraph
          highlightedNodes={highlightedNodes}
          onNodeSelect={handleNodeSelect}
          onNodeDragStart={handleNodeDragStart}
          currentRepoId={currentRepo?.local_repo_id}
        />
      </div>

      {/* Left Nav Glass Overlay */}
      <div className="absolute left-0 top-0 bottom-0 z-50">
        <LeftNav
          activeView={showHistory ? 'history' : showChats ? 'chats' : null}
          onHistoryClick={() => setShowHistory(true)}
          onChatsClick={() => setShowChats(true)}
        />
      </div>

      {/* History Panel - Phase 2: Repos */}
      <HistoryPanel
        isOpen={showHistory}
        onClose={() => setShowHistory(false)}
        onLoadRepo={async (repo) => {
          console.log('🔄 LOAD REPO FROM HISTORY:', {
            repoName: repo.repo_name,
            localRepoId: repo.local_repo_id,
            repoId: repo.id
          });

          // Activate repo in backend (sets global latest_repo_id)
          await API.post(`/api/repos/${repo.local_repo_id}/activate`);
          console.log('✅ Activate endpoint called');

          // Clear old highlighted nodes (from previous repo)
          setHighlightedNodes([]);
          console.log('✅ Cleared old highlights');

          // Set as current repo
          setCurrentRepo(repo);
          console.log('✅ currentRepo set, will trigger graph refetch');

          // Load most recent session for this repo (if user logged in)
          if (user) {
            try {
              const sessionsResponse = await API.get(`/api/user/${user.id}/repo/${repo.id}/sessions`);
              const sessions = sessionsResponse.data;

              if (sessions && sessions.length > 0) {
                const mostRecent = sessions[0];
                setChatHistory(mostRecent.messages || []);
                setSelectedNodes(mostRecent.context_nodes || []);
                setHighlightedNodes(mostRecent.highlighted_nodes || []);
                setCurrentSession(mostRecent);
                console.log('✅ Loaded most recent session');
              } else {
                // No sessions, clear chat
                setChatHistory([]);
                setSelectedNodes([]);
                setHighlightedNodes([]);
                setCurrentSession(null);
              }
            } catch (err) {
              console.error('Error loading session:', err);
            }
          }

          // Graph will refetch automatically when backend repo changes
          console.log('✅ Repo loaded:', repo.repo_name);
        }}
      />

      {/* Chat History Panel - Phase 3: Sessions for current repo */}
      <ChatHistoryPanel
        isOpen={showChats}
        onClose={() => setShowChats(false)}
        currentRepo={currentRepo}
        onLoadSession={async (session) => {
          console.log('💬 LOAD SESSION:', {
            sessionId: session.id,
            title: session.title,
            messages: session.messages?.length,
            contextNodes: session.context_nodes?.length,
            highlights: session.highlighted_nodes?.length
          });

          // Restore full chat state
          setChatHistory(session.messages || []);
          console.log('✅ Chat history set');

          setSelectedNodes(session.context_nodes || []);
          console.log('✅ Context nodes set');

          setHighlightedNodes(session.highlighted_nodes || []);
          console.log('✅ Highlighted nodes set - should trigger canvas update');

          setCurrentSession(session);
          console.log('✅ Session restored');
        }}
        onNewChat={handleNewChat}
      />

      {/* Right HUD Glass Overlay - Glass Cockpit with Neural Blue Sync */}
      <div
        ref={resizeRef}
        className="absolute right-0 top-0 bottom-0 z-50"
        style={{
          width: `${chatPanelWidth}px`,
          backgroundColor: 'rgba(9, 9, 11, 0.75)',  // More transparent for ghosting
          backdropFilter: 'blur(48px) saturate(180%)',  // blur-3xl + saturation for node ghosts
          borderLeft: selectedNodes.length > 0
            ? '1px solid rgba(34, 211, 238, 0.6)'  // Electric cyan when node selected
            : '1px solid rgba(255, 255, 255, 0.1)',  // Default white/10
          boxShadow: selectedNodes.length > 0
            ? '-2px 0 8px rgba(34, 211, 238, 0.2)'  // Cyan glow when active
            : 'none',
          transition: isResizing ? 'none' : 'box-shadow 0.3s, border-color 0.3s'
        }}
      >
        {/* Resize Handle */}
        <div
          className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize z-50 group"
          onMouseDown={(e) => {
            e.preventDefault();
            setIsResizing(true);
          }}
          style={{
            backgroundColor: isResizing ? 'rgba(59, 130, 246, 0.5)' : 'transparent'
          }}
        >
          {/* Visual indicator on hover */}
          <div
            className="absolute left-0 top-0 bottom-0 w-1 opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ backgroundColor: 'rgba(59, 130, 246, 0.3)' }}
          />
        </div>
        {/* Upload button in top-right */}
        <div className="absolute top-4 left-4 z-60">
          <button
            onClick={() => navigate('/')}
            className="px-3 py-1.5 rounded-md text-xs font-medium transition-all"
            style={{
              backgroundColor: 'transparent',
              border: '1px solid rgba(59, 130, 246, 0.3)',
              color: '#3b82f6',
              fontFamily: "'Inter', sans-serif"
            }}
            onMouseEnter={(e) => e.target.style.backgroundColor = 'rgba(59, 130, 246, 0.1)'}
            onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
          >
            Upload New Repo
          </button>
        </div>

        {/* Tabs - Terminal Style */}
        <div className="flex gap-1 mt-16 px-4" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.03)' }}>
          <button
            onClick={() => setActiveTab('chat')}
            className="px-3 py-1.5 text-[10px] font-medium transition-all"
            style={{
              color: activeTab === 'chat' ? '#e5e5e7' : '#52525b',
              backgroundColor: 'transparent',
              borderBottom: activeTab === 'chat' ? '2px solid #3b82f6' : '2px solid transparent',
              fontFamily: "'JetBrains Mono', monospace",
              textTransform: 'lowercase',
              letterSpacing: '0.02em'
            }}
          >
            chat
          </button>
          <button
            onClick={() => setActiveTab('inspector')}
            className="px-3 py-1.5 text-[10px] font-medium transition-all"
            style={{
              color: activeTab === 'inspector' ? '#e5e5e7' : '#52525b',
              backgroundColor: 'transparent',
              borderBottom: activeTab === 'inspector' ? '2px solid #3b82f6' : '2px solid transparent',
              fontFamily: "'JetBrains Mono', monospace",
              textTransform: 'lowercase',
              letterSpacing: '0.02em'
            }}
          >
            inspect
          </button>
        </div>

        {/* Tab Content */}
        <div className="h-[calc(100%-8rem)]">
          {activeTab === 'chat' ? (
            <Chatbot
              key="chat-tab"
              onSubmit={handleSubmitQuery}
              chatHistory={chatHistory}
              isLoading={isLoading}
              progressSteps={progressSteps}
              selectedNodes={selectedNodes}
              onClearContext={handleClearContext}
              onRemoveNode={handleRemoveNode}
              draggedNode={draggedNode}
              onAddNodeToContext={handleAddNodeToContext}
              onNewChat={handleNewChat}
            />
          ) : (
            <NodeInspector
              key={inspectedNode?.id || 'inspector-tab'}
              selectedNode={inspectedNode}
              onExplain={handleExplain}
              onAskQuestion={handleAskQuestion}
              currentRepoId={currentRepo?.local_repo_id}
            />
          )}
        </div>
      </div>
    </div>
  );
};

export default GraphChat;
