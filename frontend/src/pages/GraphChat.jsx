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
  const [selectedNode, setSelectedNode] = useState(null);
  const [activeTab, setActiveTab] = useState('chat');

  // Shared chat state
  const [chatHistory, setChatHistory] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [progressSteps, setProgressSteps] = useState([]);

  const navigate = useNavigate();

  const handleHighlightNodes = useCallback((nodeIds) => {
    setHighlightedNodes(nodeIds || []);
  }, []);

  const handleNodeSelect = useCallback((node) => {
    setSelectedNode(node);
    if (node) {
      setActiveTab('inspector');
    }
  }, []);

  // Main query handler
  const handleSubmitQuery = useCallback(async (queryText) => {
    if (!queryText.trim() || isLoading) return;

    setChatHistory(prev => [...prev, { type: 'user', text: queryText }]);
    setIsLoading(true);

    // Generate progress steps
    const keywords = queryText.replace(/[?.,]/g, '').split(' ').filter(w => w.length > 3).slice(0, 3);
    const steps = [
      { id: 1, message: `Searching codebase${keywords[0] ? ` for "${keywords[0]}"` : ''}...`, status: 'active' },
      { id: 2, message: 'Running semantic analysis...', status: 'pending' },
      { id: 3, message: keywords[1] ? `Analyzing ${keywords[1]} patterns...` : 'Analyzing patterns...', status: 'pending' },
      { id: 4, message: 'Expanding dependency graph...', status: 'pending' },
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
      const res = await API.post('/api/query', { query: queryText });
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
  }, [isLoading, handleHighlightNodes]);

  const handleExplain = useCallback(async (node) => {
    setActiveTab('chat');
    const name = node.label?.split('\n')[0] || node.id;
    await handleSubmitQuery(`Explain what ${name} does`);
  }, [handleSubmitQuery]);

  const handleAskQuestion = useCallback((node) => {
    setActiveTab('chat');
    const name = node.label?.split('\n')[0] || node.id;
    setChatHistory(prev => [...prev, {
      type: 'system',
      text: `Asking about: ${name}`
    }]);
  }, []);

  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ backgroundColor: '#050505' }}>
      {/* Full-bleed graph canvas */}
      <div className="absolute inset-0">
        <DependencyGraph
          highlightedNodes={highlightedNodes}
          onNodeSelect={handleNodeSelect}
        />
      </div>

      {/* Left Nav Glass Overlay */}
      <div className="absolute left-0 top-0 bottom-0 z-50">
        <LeftNav activeView="map" />
      </div>

      {/* Right HUD Glass Overlay - Deep Space */}
      <div
        className="absolute right-0 top-0 bottom-0 w-96 z-50"
        style={{
          backgroundColor: 'rgba(9, 9, 11, 0.7)',
          backdropFilter: 'blur(24px)',
          borderLeft: '1px solid rgba(255, 255, 255, 0.1)'
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

        {/* Tabs */}
        <div className="flex gap-2 mt-16 px-4" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
          <button
            onClick={() => setActiveTab('chat')}
            className="px-3 py-2 text-xs font-medium transition-all rounded-t-md"
            style={{
              color: activeTab === 'chat' ? '#f4f4f5' : '#71717a',
              backgroundColor: activeTab === 'chat' ? 'rgba(59, 130, 246, 0.1)' : 'transparent',
              border: activeTab === 'chat' ? '1px solid rgba(59, 130, 246, 0.2)' : '1px solid transparent',
              borderBottom: 'none',
              fontFamily: "'Inter', sans-serif"
            }}
          >
            Chat
          </button>
          <button
            onClick={() => setActiveTab('inspector')}
            className="px-3 py-2 text-xs font-medium transition-all rounded-t-md"
            style={{
              color: activeTab === 'inspector' ? '#f4f4f5' : '#71717a',
              backgroundColor: activeTab === 'inspector' ? 'rgba(59, 130, 246, 0.1)' : 'transparent',
              border: activeTab === 'inspector' ? '1px solid rgba(59, 130, 246, 0.2)' : '1px solid transparent',
              borderBottom: 'none',
              fontFamily: "'Inter', sans-serif"
            }}
          >
            Node Details
          </button>
        </div>

        {/* Tab Content */}
        <div className="h-[calc(100%-8rem)]">
          {activeTab === 'chat' ? (
            <Chatbot
              onSubmit={handleSubmitQuery}
              chatHistory={chatHistory}
              isLoading={isLoading}
              progressSteps={progressSteps}
              contextNode={selectedNode ? selectedNode.label?.split('\n')[0] : null}
            />
          ) : (
            <NodeInspector
              selectedNode={selectedNode}
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
