// frontend/src/pages/graphchat.jsx
import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import DependencyGraph from '../components/DependencyGraph';
import Chatbot from '../components/Chatbot';
import API from '../api';

const GraphChat = () => {
  const [graphWidth, setGraphWidth] = useState(65);
  const [highlightedNodes, setHighlightedNodes] = useState([]);
  const [nodeQuery, setNodeQuery] = useState(null);  // { query, node }
  const navigate = useNavigate();

  const handleHighlightNodes = useCallback((nodeIds) => {
    console.log('GraphChat: Highlighting nodes:', nodeIds);
    setHighlightedNodes(nodeIds || []);
  }, []);

  const handleNodeQuery = useCallback((query, node) => {
    console.log('GraphChat: Node query triggered:', query, node);
    setNodeQuery({ query, node });
    // Highlight the queried node
    setHighlightedNodes([node.id]);
  }, []);

  const handleResize = useCallback((e) => {
    const newWidth = (e.clientX / window.innerWidth) * 100;
    setGraphWidth(Math.max(30, Math.min(newWidth, 70)));
  }, []);

  useEffect(() => {
    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleResize);
    };

    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleResize);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [handleResize]);

  return (
    <div className="flex flex-col h-screen font-sans" style={{ backgroundColor: 'var(--black)', color: 'var(--text-primary)' }}>
      <header className="p-4 flex justify-between items-center" style={{
        backgroundColor: 'var(--near-black)',
        borderBottom: '1px solid var(--border-subtle)',
        height: '56px'
      }}>
        <h1 className="text-lg font-semibold" style={{ color: 'var(--accent)' }}>⚡ Visdep</h1>
        <button
          onClick={() => navigate('/')}
          className="px-4 py-2 rounded-md text-sm font-medium transition-all"
          style={{
            backgroundColor: '#84a07c',
            color: '#ffffff',
            border: 'none',
            cursor: 'pointer'
          }}
          onMouseEnter={(e) => e.target.style.opacity = '0.9'}
          onMouseLeave={(e) => e.target.style.opacity = '1'}
        >
          Upload New Repo
        </button>
      </header>
      <div className="flex flex-1 overflow-hidden">
        <div style={{ width: `${graphWidth}%`, backgroundColor: 'var(--black)' }} className="shadow-lg">
          <div className="h-full">
            <DependencyGraph
              highlightedNodes={highlightedNodes}
              onNodeQuery={handleNodeQuery}
            />
          </div>
        </div>
        <div
          className="w-1 cursor-col-resize hover:opacity-100 transition-opacity"
          style={{
            backgroundColor: 'var(--border-default)',
            opacity: 0.5
          }}
          onMouseDown={() => document.addEventListener('mousemove', handleResize)}
        />
        <div style={{ width: `${100 - graphWidth}%`, backgroundColor: 'var(--near-black)' }} className="shadow-lg flex flex-col">
          <Chatbot
            onHighlightNodes={handleHighlightNodes}
            nodeQuery={nodeQuery}
            onQueryProcessed={() => setNodeQuery(null)}
          />
        </div>
      </div>
    </div>
  );
};

export default GraphChat;