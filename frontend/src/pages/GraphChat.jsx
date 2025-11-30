// frontend/src/pages/graphchat.jsx
import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Rnd } from 'react-rnd';
import DependencyGraph from '../components/DependencyGraph';
import Chatbot from '../components/Chatbot';
import API from '../api';

const GraphChat = () => {
  const [highlightedNodes, setHighlightedNodes] = useState([]);
  const [nodeQuery, setNodeQuery] = useState(null);
  const [isChatActive, setIsChatActive] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [panelSize, setPanelSize] = useState({ width: 450, height: 600 });
  const [panelPosition, setPanelPosition] = useState({ x: 0, y: 0 });

  // Shared chat state (lifted from Chatbot)
  const [chatHistory, setChatHistory] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [progressSteps, setProgressSteps] = useState([]);

  const navigate = useNavigate();

  // Calculate initial panel position
  useEffect(() => {
    setPanelPosition({
      x: window.innerWidth - 470 - 20,
      y: 70
    });
  }, []);

  const handleHighlightNodes = useCallback((nodeIds) => {
    console.log('GraphChat: Highlighting nodes:', nodeIds);
    setHighlightedNodes(nodeIds || []);
  }, []);

  const handleNodeQuery = useCallback((query, node) => {
    console.log('GraphChat: Node query triggered:', query, node);
    setNodeQuery({ query, node });
    setHighlightedNodes([node.id]);
  }, []);

  // Main query handler (lifted from Chatbot)
  const handleSubmitQuery = useCallback(async (queryText) => {
    if (!queryText.trim()) return;

    console.log('GraphChat: Submitting query:', queryText);

    // Activate floating panel immediately
    setIsChatActive(true);
    setIsMinimized(false);

    // Add user message
    setChatHistory(prev => [...prev, { type: 'user', text: queryText }]);
    setIsLoading(true);

    // Generate progress steps
    const keywords = queryText
      .replace(/[?.,]/g, '')
      .split(' ')
      .filter(word =>
        word.length > 3 &&
        !['does', 'what', 'how', 'why', 'when', 'where', 'the', 'this', 'that', 'with', 'from', 'into'].includes(word.toLowerCase())
      )
      .slice(0, 3);

    const steps = [
      {
        id: 1,
        message: `Searching codebase for "${keywords[0] || 'relevant code'}"...`,
        status: 'active'
      },
      {
        id: 2,
        message: 'Running semantic analysis...',
        status: 'pending'
      },
      {
        id: 3,
        message: keywords[1] ? `Analyzing ${keywords[1]} patterns...` : 'Analyzing patterns...',
        status: 'pending'
      },
      {
        id: 4,
        message: 'Expanding dependency graph...',
        status: 'pending'
      },
      {
        id: 5,
        message: 'Synthesizing answer...',
        status: 'pending'
      },
      {
        id: 6,
        message: 'Generating citations...',
        status: 'pending'
      }
    ];

    setProgressSteps(steps);

    // Real-time progress updates (1 second intervals)
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
      } else if (error.response?.status === 500) {
        errorMessage = 'Server error. Please try again.';
      } else if (error.message) {
        errorMessage = `Error: ${error.message}`;
      }

      setChatHistory(prev => [...prev, { type: 'bot', text: errorMessage }]);
      console.error('Query error:', error);
    } finally {
      setIsLoading(false);
      setProgressSteps([]);
    }
  }, [handleHighlightNodes]);

  const handleChatClose = useCallback(() => {
    setIsChatActive(false);
    setChatHistory([]);
  }, []);

  const handleMinimize = useCallback(() => {
    setIsMinimized(true);
    setIsChatActive(false);
  }, []);

  const handleOpenNodeChat = useCallback((messages, parentNode) => {
    // Add messages to chat history
    setChatHistory(messages);

    // Open chat panel
    setIsChatActive(true);
    setIsMinimized(false);
  }, []);

  return (
    <div className="flex flex-col h-screen font-sans" style={{ backgroundColor: 'var(--black)', color: 'var(--text-primary)' }}>
      <header className="p-4 flex justify-between items-center" style={{
        backgroundColor: 'var(--near-black)',
        borderBottom: '1px solid var(--border-subtle)',
        height: '56px'
      }}>
        <h1 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--text-primary)', fontFamily: "'Inter', sans-serif", fontWeight: 600 }}>Visdep</h1>
        <button
          onClick={() => navigate('/')}
          className="px-4 py-2 rounded-lg text-sm font-medium transition-all"
          style={{
            backgroundColor: 'var(--accent)',
            color: '#FFFFFF',
            border: 'none',
            cursor: 'pointer',
            fontFamily: "'Inter', sans-serif",
            fontWeight: 500
          }}
          onMouseEnter={(e) => e.target.style.opacity = '0.85'}
          onMouseLeave={(e) => e.target.style.opacity = '1'}
        >
          Upload New Repo
        </button>
      </header>
      <div className="flex flex-1 overflow-hidden relative">
        {/* Full-width graph */}
        <div className="w-full h-full" style={{ backgroundColor: 'var(--black)' }}>
          <DependencyGraph
            highlightedNodes={highlightedNodes}
            onNodeQuery={handleNodeQuery}
            onOpenNodeChat={handleOpenNodeChat}
          />
        </div>

        {/* Draggable, resizable floating chat panel */}
        {isChatActive && !isMinimized && (
          <Rnd
            size={{ width: panelSize.width, height: panelSize.height }}
            position={{ x: panelPosition.x, y: panelPosition.y }}
            onDragStop={(e, d) => setPanelPosition({ x: d.x, y: d.y })}
            onResizeStop={(e, direction, ref, delta, position) => {
              setPanelSize({
                width: parseInt(ref.style.width),
                height: parseInt(ref.style.height)
              });
              setPanelPosition(position);
            }}
            minWidth={350}
            minHeight={400}
            maxWidth={800}
            maxHeight={window.innerHeight - 100}
            bounds="parent"
            style={{ zIndex: 1000 }}
            dragHandleClassName="chat-drag-handle"
            enableResizing={{
              top: true,
              right: true,
              bottom: true,
              left: true,
              topRight: true,
              bottomRight: true,
              bottomLeft: true,
              topLeft: true
            }}
          >
            <div
              className="h-full flex flex-col rounded-lg shadow-2xl overflow-hidden"
              style={{
                backgroundColor: 'var(--card-bg)',
                border: '1px solid var(--border-default)'
              }}
            >
              <Chatbot
                isRightPanel={true}
                onClose={handleChatClose}
                onMinimize={handleMinimize}
                onSubmit={handleSubmitQuery}
                chatHistory={chatHistory}
                isLoading={isLoading}
                progressSteps={progressSteps}
              />
            </div>
          </Rnd>
        )}

        {/* Bottom floating input */}
        {!isChatActive && (
          <div className="absolute bottom-8 left-1/2 transform -translate-x-1/2 z-10">
            <Chatbot
              isRightPanel={false}
              onSubmit={handleSubmitQuery}
            />
          </div>
        )}
      </div>
    </div>
  );
};

export default GraphChat;
