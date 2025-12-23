// frontend/src/pages/graphchat.jsx
import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
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

  // Sync ref with state (no re-render, just tracking)
  useEffect(() => {
    selectedNodesRef.current = selectedNodes;
  }, [selectedNodes]);

  // Phase 3: Initialize currentRepo from sessionStorage after upload
  useEffect(() => {
    const storedRepo = sessionStorage.getItem('visdep_current_repo');
    if (storedRepo && !currentRepo) {
      const repo = JSON.parse(storedRepo);
      setCurrentRepo(repo);
      sessionStorage.removeItem('visdep_current_repo');
      console.log('✅ Initialized currentRepo:', repo.repo_name);
    }
  }, [currentRepo]);

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

  // Main query handler with node context support
  const handleSubmitQuery = useCallback(async (queryText, nodeContext = null) => {
    if (!queryText.trim() || isLoading) return;

    const newMessage = { type: 'user', text: queryText };
    setChatHistory(prev => [...prev, newMessage]);
    setIsLoading(true);

    // Use selectedNodes if no explicit nodeContext provided
    const contextNodes = nodeContext ? [nodeContext] : selectedNodes;

    // Generate progress steps - show node context if present
    const keywords = queryText.replace(/[?.,]/g, '').split(' ').filter(w => w.length > 3).slice(0, 3);
    const nodeCount = contextNodes.length;
    const nodeName = nodeCount === 1 ? (contextNodes[0].label?.split('\n')[0] || contextNodes[0].id) : `${nodeCount} nodes`;

    const steps = [
      { id: 1, message: nodeCount > 0 ? `Analyzing ${nodeName}...` : `Searching codebase${keywords[0] ? ` for "${keywords[0]}"` : ''}...`, status: 'active' },
      { id: 2, message: 'Running semantic analysis...', status: 'pending' },
      { id: 3, message: keywords[1] ? `Analyzing ${keywords[1]} patterns...` : 'Analyzing patterns...', status: 'pending' },
      { id: 4, message: nodeCount > 0 ? `Fetching ${nodeName} context...` : 'Expanding dependency graph...', status: 'pending' },
      { id: 5, message: 'Synthesizing answer...', status: 'pending' },
      { id: 6, message: 'Generating citations...', status: 'pending' }
    ];

    setProgressSteps(steps);

    const progressInterval = setInterval(() => {
      setProgressSteps(prev => {
        const activeIndex = prev.findIndex(s => s.status === 'active');
        if (activeIndex < prev.length - 1) {
          return prev.map((s, i) => ({
            ...s,
            status: i <= activeIndex ? 'complete' : i === activeIndex + 1 ? 'active' : 'pending'
          }));
        }
        return prev;
      });
    }, 1000);

    try {
      // OPTION C EXTENDED: Send node_contexts for multi-node queries
      const payload = { query: queryText };

      if (contextNodes.length > 0) {
        payload.node_contexts = contextNodes.map(node => ({
          chunk_id: node.id,
          name: node.label?.split('\n')[0] || node.id,
          type: node.type
        }));
      }

      const res = await API.post('/api/query', payload);
      clearInterval(progressInterval);

      const responseText = res.data.response || res.data;
      const botMessage = { type: 'bot', text: responseText };
      setChatHistory(prev => [...prev, botMessage]);

      if (res.data.highlighted_nodes) {
        handleHighlightNodes(res.data.highlighted_nodes);
      }

      // Phase 3: Auto-save session after query
      if (currentSession && user) {
        const updatedMessages = [...chatHistory, newMessage, botMessage];

        // Generate title from first query
        const sessionTitle = currentSession.title || queryText.substring(0, 50);

        // Auto-save (debounced, non-blocking)
        setTimeout(async () => {
          try {
            await API.put(`/api/sessions/${currentSession.id}`, {
              messages: updatedMessages,
              context_nodes: selectedNodes.map(n => ({
                chunk_id: n.id,
                name: n.label?.split('\n')[0],
                type: n.type
              })),
              highlighted_nodes: res.data.highlighted_nodes || [],  // Save graph state
              title: sessionTitle
            });
            console.log('💾 Session auto-saved');
          } catch (err) {
            console.error('⚠️ Auto-save failed:', err);
          }
        }, 500);
      }
    } catch (error) {
      clearInterval(progressInterval);

      let errorMessage = 'Error querying Visdep';
      if (error.response?.status === 400) {
        errorMessage = error.response.data?.detail || 'Please upload a repository first.';
      }

      setChatHistory(prev => [...prev, { type: 'bot', text: errorMessage }]);
    } finally {
      setIsLoading(false);
      setProgressSteps([]);
    }
  }, [isLoading, handleHighlightNodes, selectedNodes]);

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
          activeView="map"
          onHistoryClick={() => setShowHistory(true)}
          onChatsClick={() => setShowChats(true)}
        />
      </div>

      {/* History Panel - Phase 2: Repos */}
      <HistoryPanel
        isOpen={showHistory}
        onClose={() => setShowHistory(false)}
        onLoadRepo={async (repo) => {
          console.log('Loading repo from history:', repo);

          // Activate repo in backend (sets global latest_repo_id)
          await API.post(`/api/repos/${repo.local_repo_id}/activate`);

          // Set as current repo
          setCurrentRepo(repo);

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
          console.log('Loading session:', session);

          // Restore full chat state
          setChatHistory(session.messages || []);
          setSelectedNodes(session.context_nodes || []);
          setHighlightedNodes(session.highlighted_nodes || []);
          setCurrentSession(session);

          console.log('✅ Session restored');
        }}
        onNewChat={handleNewChat}
      />

      {/* Right HUD Glass Overlay - Glass Cockpit with Neural Blue Sync */}
      <div
        className="absolute right-0 top-0 bottom-0 w-96 z-50 transition-all duration-300"
        style={{
          backgroundColor: 'rgba(9, 9, 11, 0.75)',  // More transparent for ghosting
          backdropFilter: 'blur(48px) saturate(180%)',  // blur-3xl + saturation for node ghosts
          borderLeft: selectedNodes.length > 0
            ? '1px solid rgba(34, 211, 238, 0.6)'  // Electric cyan when node selected
            : '1px solid rgba(255, 255, 255, 0.1)',  // Default white/10
          boxShadow: selectedNodes.length > 0
            ? '-2px 0 8px rgba(34, 211, 238, 0.2)'  // Cyan glow when active
            : 'none'
        }}
      >
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
            />
          )}
        </div>
      </div>
    </div>
  );
};

export default GraphChat;
