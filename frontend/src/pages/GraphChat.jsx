// frontend/src/pages/graphchat.jsx
import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import DependencyGraph from '../components/DependencyGraph';
import Chatbot from '../components/Chatbot';
import LeftNav from '../components/LeftNav';
import NodeInspector from '../components/NodeInspector';
import API from '../api';

const GraphChat = () => {
  const [highlightedNodes, setHighlightedNodes] = useState([]);
  const [selectedNodes, setSelectedNodes] = useState([]);  // Multi-node selection
  const [activeTab, setActiveTab] = useState('chat');
  const [draggedNode, setDraggedNode] = useState(null);  // Currently dragging node

  // Shared chat state
  const [chatHistory, setChatHistory] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [progressSteps, setProgressSteps] = useState([]);

  const navigate = useNavigate();

  const handleHighlightNodes = useCallback((nodeIds) => {
    setHighlightedNodes(nodeIds || []);
  }, []);

  const handleNodeSelect = useCallback((node, event) => {
    if (!node) {
      // Clear selection
      setSelectedNodes([]);
      return;
    }

    // Multi-select with Cmd/Ctrl+click
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
    } else {
      // Single select (replace)
      setSelectedNodes([node]);
      setActiveTab('inspector');
    }
  }, []);

  // Main query handler with node context support
  const handleSubmitQuery = useCallback(async (queryText, nodeContext = null) => {
    if (!queryText.trim() || isLoading) return;

    setChatHistory(prev => [...prev, { type: 'user', text: queryText }]);
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
      setChatHistory(prev => [...prev, { type: 'bot', text: responseText }]);

      if (res.data.highlighted_nodes) {
        handleHighlightNodes(res.data.highlighted_nodes);
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
    setActiveTab('chat');
    // Set the node as selected so future queries use it as context
    setSelectedNodes([node]);
  }, []);

  const handleClearContext = useCallback(() => {
    setSelectedNodes([]);
  }, []);

  const handleRemoveNode = useCallback((index) => {
    setSelectedNodes(prev => prev.filter((_, i) => i !== index));
  }, []);

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

  const handleNodeDragStart = useCallback((node) => {
    setDraggedNode(node);
  }, []);

  const handleNodeDragEnd = useCallback((mousePos) => {
    if (!draggedNode) {
      setDraggedNode(null);
      return;
    }

    // Check if dropped over chat area (right 384px of screen)
    const windowWidth = window.innerWidth;
    const chatAreaLeft = windowWidth - 384;  // w-96 = 384px

    const isOverChat = mousePos.x >= chatAreaLeft;

    if (isOverChat) {
      console.log('✅ Dropped on chat area, adding to context');
      handleAddNodeToContext(draggedNode);
    } else {
      console.log('❌ Dropped outside chat area');
    }

    setDraggedNode(null);
  }, [draggedNode, handleAddNodeToContext]);

  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ backgroundColor: '#050505' }}>
      {/* Full-bleed graph canvas */}
      <div className="absolute inset-0">
        <DependencyGraph
          highlightedNodes={highlightedNodes}
          onNodeSelect={handleNodeSelect}
          onNodeDragStart={handleNodeDragStart}
          onNodeDragEnd={handleNodeDragEnd}
        />
      </div>

      {/* Left Nav Glass Overlay */}
      <div className="absolute left-0 top-0 bottom-0 z-50">
        <LeftNav activeView="map" />
      </div>

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

        {/* Tab Content - Key forces animation on tab switch */}
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
            />
          ) : (
            <NodeInspector
              key={selectedNodes[0]?.id || 'inspector-tab'}
              selectedNode={selectedNodes[0] || null}
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
