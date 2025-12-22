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

  // Get node color for focus border
  const getNodeColor = (type) => {
    const colors = {
      file: '#3b82f6',
      class_definition: '#8b5cf6',
      function: '#3b82f6',
      method: '#a78bfa',
      directory: '#71717a'
    };
    return colors[type] || '#3b82f6';
  };

  if (!selectedNode) {
    return (
      <div className="flex flex-col items-center justify-center h-full" style={{ padding: '0 24px' }}>
        {/* Empty State - System Ready */}
        <pre style={{
          fontSize: '9px',
          color: '#27272a',
          fontFamily: "'JetBrains Mono', monospace",
          lineHeight: '1.2',
          marginBottom: '16px',
          textAlign: 'center'
        }}>
{`    ╔══════════════╗
    ║   VISDEP     ║
    ║   READY      ║
    ╚══════════════╝`}
        </pre>
        <p style={{
          fontSize: '11px',
          color: '#52525b',
          fontFamily: "'JetBrains Mono', monospace",
          textAlign: 'center'
        }}>
          {'// Click any node to inspect'}
        </p>
      </div>
    );
  }

  const nodeName = selectedNode.label?.split('\n')[0] || selectedNode.id;
  const nodeType = selectedNode.type || 'unknown';
  const nodeColor = getNodeColor(nodeType);

  // Extract metadata
  const filePath = selectedNode.id || 'unknown';
  const hasCode = nodeCode && nodeCode.trim().length > 0;
  const codePreview = hasCode ? nodeCode.split('\n').slice(0, 10).join('\n') : null;

  return (
    <div
      className="flex flex-col h-full overflow-auto relative animate-slide-in"
      style={{
        backgroundColor: 'rgba(9, 9, 11, 0.75)',  // Slightly more transparent for ghosting
        backdropFilter: 'blur(48px) saturate(180%)',  // blur-3xl + saturation
        borderLeft: `1px solid ${nodeColor}40`  // Neon focus border
      }}
    >
      {/* Dense Metadata Header */}
      <div style={{ padding: '16px 16px 12px 16px' }}>
        {/* Node Name */}
        <h3 style={{
          fontSize: '13px',
          fontWeight: 600,
          color: '#f4f4f5',
          fontFamily: "'Inter', sans-serif",
          marginBottom: '8px',
          letterSpacing: '-0.01em',
          lineHeight: 1.2
        }}>
          {nodeName}
        </h3>

        {/* Metadata Grid - Dense Layout */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <MetadataRow label="type" value={nodeType} />
          <MetadataRow label="path" value={filePath} />
          {hasCode && (
            <MetadataRow
              label="lines"
              value={`${nodeCode.split('\n').length} LOC`}
            />
          )}
        </div>
      </div>

      {/* Code Portal - Mini Editor */}
      <div style={{ padding: '0 16px 16px 16px', flex: 1 }}>
        {loading ? (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '11px',
            color: '#71717a',
            fontFamily: "'JetBrains Mono', monospace"
          }}>
            <div
              className="animate-spin"
              style={{
                width: '10px',
                height: '10px',
                border: '2px solid #3b82f6',
                borderTopColor: 'transparent',
                borderRadius: '50%'
              }}
            />
            loading...
          </div>
        ) : codePreview ? (
          <>
            {/* Label */}
            <div style={{
              fontSize: '9px',
              color: '#52525b',
              fontFamily: "'JetBrains Mono', monospace",
              textTransform: 'uppercase',
              letterSpacing: '0.8px',
              marginBottom: '6px',
              fontWeight: 500
            }}>
              &gt; CODE PREVIEW
            </div>

            {/* Pure Black Code Block */}
            <SyntaxHighlighter
              language="python"
              style={vscDarkPlus}
              customStyle={{
                backgroundColor: '#000000',  // Pure black - mini editor
                padding: '10px 12px',
                borderRadius: '3px',
                fontSize: '10px',
                fontFamily: "'JetBrains Mono', monospace",
                border: '1px solid rgba(255, 255, 255, 0.05)',
                margin: 0,
                lineHeight: '1.4',
                maxHeight: '300px',
                overflow: 'auto'
              }}
              showLineNumbers={false}
            >
              {codePreview}
            </SyntaxHighlighter>

            {nodeCode.split('\n').length > 10 && (
              <div style={{
                fontSize: '10px',
                color: '#52525b',
                fontFamily: "'JetBrains Mono', monospace",
                marginTop: '6px',
                fontStyle: 'italic'
              }}>
                // Showing first 10 lines
              </div>
            )}
          </>
        ) : (
          <div style={{
            fontSize: '11px',
            color: '#52525b',
            fontFamily: "'JetBrains Mono', monospace"
          }}>
            {'// No code preview available'}
          </div>
        )}

        {/* Action Buttons - Compact */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '16px' }}>
          <button
            onClick={() => onExplain(selectedNode)}
            style={{
              width: '100%',
              padding: '8px 12px',
              borderRadius: '3px',
              fontSize: '11px',
              fontWeight: 500,
              fontFamily: "'JetBrains Mono', monospace",
              backgroundColor: 'rgba(59, 130, 246, 0.12)',
              border: '1px solid rgba(59, 130, 246, 0.3)',
              color: '#60a5fa',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              textTransform: 'lowercase',
              letterSpacing: '0.02em'
            }}
            onMouseEnter={(e) => {
              e.target.style.backgroundColor = 'rgba(59, 130, 246, 0.18)';
              e.target.style.borderColor = 'rgba(59, 130, 246, 0.4)';
            }}
            onMouseLeave={(e) => {
              e.target.style.backgroundColor = 'rgba(59, 130, 246, 0.12)';
              e.target.style.borderColor = 'rgba(59, 130, 246, 0.3)';
            }}
          >
            explain
          </button>
          <button
            onClick={() => onAskQuestion(selectedNode)}
            style={{
              width: '100%',
              padding: '8px 12px',
              borderRadius: '3px',
              fontSize: '11px',
              fontWeight: 500,
              fontFamily: "'JetBrains Mono', monospace",
              backgroundColor: 'rgba(255, 255, 255, 0.03)',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              color: '#a1a1aa',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              textTransform: 'lowercase',
              letterSpacing: '0.02em'
            }}
            onMouseEnter={(e) => {
              e.target.style.backgroundColor = 'rgba(255, 255, 255, 0.06)';
              e.target.style.borderColor = 'rgba(255, 255, 255, 0.12)';
            }}
            onMouseLeave={(e) => {
              e.target.style.backgroundColor = 'rgba(255, 255, 255, 0.03)';
              e.target.style.borderColor = 'rgba(255, 255, 255, 0.08)';
            }}
          >
            ask question
          </button>
        </div>
      </div>
    </div>
  );
};

// Dense Metadata Row Component
const MetadataRow = ({ label, value }) => (
  <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
    <span style={{
      fontSize: '10px',
      color: '#52525b',
      fontFamily: "'JetBrains Mono', monospace",
      textTransform: 'lowercase',
      minWidth: '40px',
      letterSpacing: '0.01em'
    }}>
      {label}:
    </span>
    <span style={{
      fontSize: '11px',
      color: '#e5e5e7',
      fontFamily: "'Inter', sans-serif",
      flex: 1,
      wordBreak: 'break-all',
      lineHeight: '1.4'
    }}>
      {value}
    </span>
  </div>
);

// Add slide-in animation CSS
const styles = `
  @keyframes slide-in-right {
    from {
      opacity: 0;
      transform: translateX(20px);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }

  .animate-slide-in {
    animation: slide-in-right 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  }
`;

// Inject styles
if (typeof document !== 'undefined' && !document.getElementById('inspector-animations')) {
  const styleSheet = document.createElement('style');
  styleSheet.id = 'inspector-animations';
  styleSheet.textContent = styles;
  document.head.appendChild(styleSheet);
}

export default NodeInspector;
