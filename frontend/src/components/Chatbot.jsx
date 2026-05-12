import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

const Chatbot = ({ onSubmit, chatHistory = [], isLoading = false, progressSteps = [], selectedNodes = [], onClearContext = null, onRemoveNode = null, draggedNode = null, onAddNodeToContext = null, onNewChat = null }) => {
  const [query, setQuery] = useState('');
  const chatContainerRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [chatHistory, progressSteps]);

  // CMD+K to focus input (global shortcut)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleSubmit = (e) => {
    if (e) e.preventDefault();
    if (!query.trim() || isLoading) return;

    onSubmit(query);
    setQuery('');
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInputChange = (e) => {
    setQuery(e.target.value);
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = Math.min(inputRef.current.scrollHeight, 200) + 'px';
    }
  };

  const renderMessage = (msg) => {
    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ node, inline, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            return !inline ? (
              <SyntaxHighlighter
                style={vscDarkPlus}
                language={match ? match[1] : 'python'}
                PreTag="div"
                customStyle={{
                  backgroundColor: '#000000',  // Pure black - high-end editor look
                  padding: '10px 12px',
                  borderRadius: '2px',  // Sharper corners
                  fontSize: '11px',
                  fontFamily: "'JetBrains Mono', monospace",
                  margin: '6px 0 6px 0',  // Tighter margins
                  border: '1px solid rgba(255, 255, 255, 0.05)',  // Subtle white border
                  lineHeight: '1.4'  // Compact code
                }}
                {...props}
              >
                {String(children).replace(/\n$/, '')}
              </SyntaxHighlighter>
            ) : (
              <code
                style={{
                  backgroundColor: 'rgba(59, 130, 246, 0.12)',
                  color: '#60a5fa',
                  padding: '2px 5px',
                  borderRadius: '2px',
                  fontSize: '11px',
                  fontFamily: "'JetBrains Mono', monospace"
                }}
                {...props}
              >
                {children}
              </code>
            );
          },
          p: ({ children }) => <p style={{ margin: '0 0 6px 0', lineHeight: '1.45', fontSize: '12px', color: '#e5e5e7' }}>{children}</p>,
          h2: ({ children }) => <h2 style={{ fontSize: '13px', fontWeight: 600, margin: '10px 0 4px 0', color: '#f4f4f5', letterSpacing: '-0.01em' }}>{children}</h2>,
          ul: ({ children }) => <ul style={{ margin: '4px 0 4px 0', paddingLeft: '18px', lineHeight: '1.4' }}>{children}</ul>,
          li: ({ children }) => <li style={{ margin: '2px 0', fontSize: '12px', color: '#e5e5e7' }}>{children}</li>,
          strong: ({ children }) => <strong style={{ fontWeight: 600, color: '#f4f4f5' }}>{children}</strong>,
          a: ({ href, children }) => <a href={href} style={{ color: '#3b82f6', textDecoration: 'none' }} target="_blank" rel="noopener noreferrer">{children}</a>,
        }}
      >
        {msg.text}
      </ReactMarkdown>
    );
  };

  return (
    <div className="flex flex-col h-full animate-slide-in relative" style={{ backgroundColor: '#050505' }}>

      {/* Intelligence Stream - Terminal Layout */}
      <div
        ref={chatContainerRef}
        className="flex-1 overflow-y-auto px-4 py-4"
        style={{ backgroundColor: '#050505' }}
      >
        {chatHistory.length === 0 && !isLoading && (
          <div className="flex flex-col items-start justify-center h-full" style={{ paddingLeft: '2px' }}>
            <p style={{ fontSize: '11px', color: '#52525b', fontFamily: "'JetBrains Mono', monospace", marginBottom: '8px' }}>
              {'// Type your query below'}
            </p>
            <p style={{ fontSize: '11px', color: '#3f3f46', fontFamily: "'JetBrains Mono', monospace" }}>
              {'// Press CMD+K to focus input'}
            </p>
          </div>
        )}

        {chatHistory.map((msg, index) => (
          <div
            key={index}
            style={{
              marginBottom: '10px',
              paddingLeft: msg.type === 'bot' ? '10px' : '2px',
              borderLeft: msg.type === 'bot' ? '2px solid rgba(59, 130, 246, 0.4)' : 'none'
            }}
          >
            {/* Compact Label - Terminal Style */}
            <div style={{
              fontSize: '9px',
              color: msg.type === 'bot' ? '#52525b' : '#3f3f46',
              marginBottom: '3px',
              fontFamily: "'JetBrains Mono', monospace",
              textTransform: 'uppercase',
              letterSpacing: '0.8px',
              fontWeight: 500
            }}>
              {msg.type === 'user' ? '> USER' : '> AGENT'}
            </div>
            {/* Message - Dense Layout */}
            <div style={{
              fontSize: '12px',
              lineHeight: '1.45',
              color: '#e5e5e7'
            }}>
              {renderMessage(msg)}
            </div>
          </div>
        ))}

        {/* Live Progress - Real-time SSE Updates */}
        {isLoading && progressSteps.length > 0 && (
          <div style={{ padding: '10px 0 0 10px', borderLeft: '2px solid rgba(59, 130, 246, 0.4)' }}>
            <div style={{ fontSize: '9px', color: '#52525b', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.8px', fontFamily: "'JetBrains Mono', monospace", fontWeight: 500 }}>
              &gt; AGENT
            </div>
            {progressSteps.map(step => (
              <div key={step.id} style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '8px',
                marginBottom: '6px',
                opacity: step.status === 'complete' ? 0.5 : 1,
                transition: 'opacity 0.3s ease'
              }}>
                {/* Status indicator */}
                {step.status === 'active' ? (
                  <div
                    className="animate-pulse"
                    style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      backgroundColor: '#3b82f6',
                      marginTop: '4px',
                      flexShrink: 0
                    }}
                  />
                ) : step.status === 'complete' ? (
                  <div style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: '#22c55e',
                    marginTop: '4px',
                    flexShrink: 0
                  }} />
                ) : (
                  <div style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: '#ef4444',
                    marginTop: '4px',
                    flexShrink: 0
                  }} />
                )}

                {/* Message and detail */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <span style={{
                    fontSize: '11px',
                    color: step.status === 'active' ? '#a1a1aa' : '#52525b',
                    fontFamily: "'JetBrains Mono', monospace"
                  }}>
                    {step.message}
                  </span>
                  {step.detail && (
                    <div style={{
                      fontSize: '10px',
                      color: '#3f3f46',
                      fontFamily: "'JetBrains Mono', monospace",
                      marginTop: '2px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap'
                    }}>
                      → {step.detail}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Command Line Input - Pure Terminal */}
      <div
        className="px-4 py-2.5"
        style={{
          borderTop: '1px solid rgba(255, 255, 255, 0.03)',
          backgroundColor: '#050505'
        }}
      >
        {/* New Chat Button - Above Context Badges */}
        {onNewChat && (
          <button
            onClick={onNewChat}
            className="mb-2 px-2 py-1.5 rounded transition-all"
            style={{
              backgroundColor: 'transparent',
              border: '1px solid rgba(63, 63, 70, 0.5)',
              color: '#52525b',
              fontSize: '9px',
              fontFamily: "'JetBrains Mono', monospace",
              letterSpacing: '0.02em',
              width: 'fit-content'
            }}
            onMouseEnter={(e) => {
              e.target.style.borderColor = '#22d3ee';
              e.target.style.color = '#22d3ee';
            }}
            onMouseLeave={(e) => {
              e.target.style.borderColor = 'rgba(63, 63, 70, 0.5)';
              e.target.style.color = '#52525b';
            }}
          >
            + new chat
          </button>
        )}

        {/* Context Badges - Multi-Node Support with Drop Zone */}
        {selectedNodes.length > 0 && onClearContext ? (
          <div
            className="mb-2 transition-all"
            style={{
              border: draggedNode ? '1px dashed rgba(34, 211, 238, 0.6)' : 'none',
              borderRadius: '4px',
              padding: draggedNode ? '6px' : '0'
            }}
          >
            {selectedNodes.length === 1 ? (
              // Single node - compact badge
              <div
                className="flex items-center gap-2 px-2 py-1.5 rounded transition-all"
                style={{
                  backgroundColor: 'rgba(24, 24, 27, 0.6)',
                  border: '1px solid rgba(63, 63, 70, 0.5)',
                  width: 'fit-content'
                }}
              >
                <span style={{
                  fontSize: '10px',
                  color: '#71717a',
                  fontFamily: "'JetBrains Mono', monospace",
                  letterSpacing: '0.02em',
                  textTransform: 'uppercase'
                }}>
                  [context: {selectedNodes[0].label?.split('\n')[0]}]
                </span>
                <button
                  onClick={onClearContext}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#52525b',
                    cursor: 'pointer',
                    fontSize: '16px',
                    lineHeight: 1,
                    padding: '0 2px',
                    transition: 'color 0.2s'
                  }}
                  onMouseEnter={(e) => e.target.style.color = '#22d3ee'}
                  onMouseLeave={(e) => e.target.style.color = '#52525b'}
                  title="Clear context (query entire codebase)"
                >
                  ×
                </button>
              </div>
            ) : (
              // Multi-node - show all badges
              <div className="flex flex-wrap gap-1">
                {selectedNodes.map((node, i) => (
                  <div
                    key={node.id}
                    className="flex items-center gap-1 px-2 py-1 rounded transition-all"
                    style={{
                      backgroundColor: 'rgba(24, 24, 27, 0.6)',
                      border: '1px solid rgba(63, 63, 70, 0.5)'
                    }}
                  >
                    <span style={{
                      fontSize: '9px',
                      color: '#71717a',
                      fontFamily: "'JetBrains Mono', monospace",
                      letterSpacing: '0.01em'
                    }}>
                      {node.label?.split('\n')[0]}
                    </span>
                    <button
                      onClick={() => onRemoveNode(i)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: '#52525b',
                        cursor: 'pointer',
                        fontSize: '14px',
                        lineHeight: 1,
                        padding: '0 2px',
                        transition: 'color 0.2s'
                      }}
                      onMouseEnter={(e) => e.target.style.color = '#22d3ee'}
                      onMouseLeave={(e) => e.target.style.color = '#52525b'}
                      title="Remove from context"
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  onClick={onClearContext}
                  style={{
                    background: 'transparent',
                    border: '1px solid rgba(63, 63, 70, 0.5)',
                    borderRadius: '3px',
                    color: '#52525b',
                    cursor: 'pointer',
                    fontSize: '9px',
                    padding: '4px 6px',
                    fontFamily: "'JetBrains Mono', monospace",
                    transition: 'all 0.2s'
                  }}
                  onMouseEnter={(e) => {
                    e.target.style.borderColor = '#22d3ee';
                    e.target.style.color = '#22d3ee';
                  }}
                  onMouseLeave={(e) => {
                    e.target.style.borderColor = 'rgba(63, 63, 70, 0.5)';
                    e.target.style.color = '#52525b';
                  }}
                  title="Clear all context"
                >
                  clear all
                </button>
              </div>
            )}
          </div>
        ) : draggedNode ? (
          // Empty state - show drop target when dragging
          <div
            className="mb-2 px-3 py-2 rounded transition-all"
            style={{
              border: '1px dashed rgba(34, 211, 238, 0.6)',
              backgroundColor: 'rgba(34, 211, 238, 0.05)'
            }}
          >
            <div style={{
              fontSize: '10px',
              color: '#52525b',
              fontFamily: "'JetBrains Mono', monospace",
              textAlign: 'center',
              letterSpacing: '0.02em'
            }}>
              {/* drop here to add to context */}
              drop here to add to context
            </div>
          </div>
        ) : null}

        <div className="flex items-start gap-2">
          <span style={{
            color: '#3b82f6',
            fontSize: '13px',
            fontFamily: "'JetBrains Mono', monospace",
            fontWeight: 600,
            lineHeight: 1.5,
            paddingTop: '4px',
            flexShrink: 0
          }}>
            &gt;
          </span>
          <textarea
            ref={inputRef}
            rows={1}
            value={query}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            placeholder={selectedNodes.length === 1 ? `query: ${selectedNodes[0].label?.split('\n')[0]}` : selectedNodes.length > 1 ? `query: ${selectedNodes.length} nodes` : 'query codebase'}
            className="flex-1 px-0 py-1 text-sm focus:outline-none transition-all bg-transparent command-input"
            style={{
              color: '#e5e5e7',
              border: 'none',
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '12px',
              opacity: isLoading ? 0.4 : 1,
              caretColor: '#3b82f6',
              letterSpacing: '-0.01em',
              resize: 'none',
              overflowY: 'auto',
              lineHeight: '1.5',
              minHeight: '20px',
              maxHeight: '200px'
            }}
          />
        </div>
      </div>

      {/* Animations */}
      <style>{`
        @keyframes pulse-caret {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
        .command-input:focus {
          animation: pulse-caret 1.2s ease-in-out infinite;
        }

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
      `}</style>
    </div>
  );
};

export default Chatbot;
