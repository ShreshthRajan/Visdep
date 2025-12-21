import React, { useState, useEffect } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import API from '../api';

const NodeInspector = ({ selectedNode, onExplain, onAskQuestion }) => {
  const [nodeCode, setNodeCode] = useState(null);
  const [loading, setLoading] = useState(false);

  // Fetch code when node selected
  useEffect(() => {
    if (!selectedNode) {
      setNodeCode(null);
      return;
    }

    const fetchCode = async () => {
      setLoading(true);
      try {
        // Extract code from chunks (already in database)
        const response = await API.get(`/api/node_code/${encodeURIComponent(selectedNode.id)}`);
        setNodeCode(response.data.code);
      } catch (error) {
        console.error('Failed to fetch code:', error);
        setNodeCode(null);
      } finally {
        setLoading(false);
      }
    };

    fetchCode();
  }, [selectedNode]);

  if (!selectedNode) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm" style={{ color: '#71717a', fontFamily: "'Inter', sans-serif" }}>
          Select a node to inspect
        </p>
      </div>
    );
  }

  const filename = selectedNode.label?.split('\n')[0] || selectedNode.id;
  const nodeType = selectedNode.type || 'unknown';

  return (
    <div className="flex flex-col h-full overflow-auto" style={{ backgroundColor: '#050505' }}>
      {/* Header */}
      <div className="p-4 border-b sticky top-0" style={{ borderColor: 'rgba(255, 255, 255, 0.08)', backgroundColor: '#050505' }}>
        <h3 className="text-sm font-semibold mb-1" style={{ color: '#f4f4f5', fontFamily: "'Inter', sans-serif" }}>
          {filename}
        </h3>
        <p className="text-xs" style={{ color: '#71717a' }}>
          {nodeType}
        </p>
      </div>

      {/* Code Preview */}
      <div className="flex-1 p-4">
        {loading ? (
          <div className="flex items-center gap-2 text-xs" style={{ color: '#71717a' }}>
            <div className="animate-spin w-3 h-3 border border-blue-500 border-t-transparent rounded-full" />
            Loading code...
          </div>
        ) : nodeCode ? (
          <SyntaxHighlighter
            language="python"
            style={vscDarkPlus}
            customStyle={{
              backgroundColor: '#0a0a0a',
              padding: '12px',
              borderRadius: '6px',
              fontSize: '11px',
              fontFamily: "'JetBrains Mono', monospace",
              border: '1px solid rgba(255, 255, 255, 0.08)',
              margin: 0
            }}
          >
            {nodeCode}
          </SyntaxHighlighter>
        ) : (
          <p className="text-xs" style={{ color: '#71717a' }}>
            No code preview available
          </p>
        )}

        {/* Actions */}
        <div className="space-y-2 mt-4">
          <button
            onClick={() => onExplain(selectedNode)}
            className="w-full px-4 py-2.5 rounded-md text-sm font-medium transition-all"
            style={{
              backgroundColor: 'rgba(59, 130, 246, 0.1)',
              border: '1px solid rgba(59, 130, 246, 0.2)',
              color: '#3b82f6',
              fontFamily: "'Inter', sans-serif"
            }}
            onMouseEnter={(e) => e.target.style.backgroundColor = 'rgba(59, 130, 246, 0.15)'}
            onMouseLeave={(e) => e.target.style.backgroundColor = 'rgba(59, 130, 246, 0.1)'}
          >
            Explain This
          </button>
          <button
            onClick={() => onAskQuestion(selectedNode)}
            className="w-full px-4 py-2.5 rounded-md text-sm font-medium transition-all"
            style={{
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              color: '#f4f4f5',
              fontFamily: "'Inter', sans-serif"
            }}
            onMouseEnter={(e) => e.target.style.backgroundColor = 'rgba(255, 255, 255, 0.08)'}
            onMouseLeave={(e) => e.target.style.backgroundColor = 'rgba(255, 255, 255, 0.05)'}
          >
            Ask Question
          </button>
        </div>
      </div>
    </div>
  );
};

export default NodeInspector;
