import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import API from '../api';

/**
 * Inline Node Chat Panel
 *
 * Appears when clicking a graph node - provides fast, focused queries
 * about that specific code chunk without regenerating the graph.
 *
 * Similar to Rabbit Hole's inline chat on nodes.
 */
const NodeChatPanel = ({ node, onClose, position }) => {
  const [query, setQuery] = useState('');
  const [conversation, setConversation] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const inputRef = useRef(null);

  // Auto-focus input when panel appears
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.focus();
    }
  }, []);

  const handleSubmit = async () => {
    if (!query.trim() || isLoading) return;

    const userMessage = query;
    setQuery('');
    setConversation(prev => [...prev, { type: 'user', text: userMessage }]);
    setIsLoading(true);

    try {
      // Node-focused query - faster than general queries
      const response = await API.post('/api/query', {
        query: userMessage
      });

      const responseText = response.data.response || response.data;
      setConversation(prev => [...prev, { type: 'bot', text: responseText }]);
    } catch (error) {
      console.error('Node query error:', error);
      setConversation(prev => [...prev, {
        type: 'bot',
        text: 'Error: Could not process query. Please try again.'
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const renderMessage = (msg) => {
    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ node, inline, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            const language = match ? match[1] : 'text';

            return !inline ? (
              <SyntaxHighlighter
                style={vscDarkPlus}
                language={language}
                PreTag="div"
                customStyle={{
                  backgroundColor: 'var(--code-bg)',
                  padding: '0.75rem',
                  borderRadius: '0.375rem',
                  fontSize: '0.75rem',
                  fontFamily: "'JetBrains Mono', monospace",
                  margin: '0.25rem 0'
                }}
                {...props}
              >
                {String(children).replace(/\n$/, '')}
              </SyntaxHighlighter>
            ) : (
              <code
                className="px-1 py-0.5 rounded text-xs"
                style={{
                  backgroundColor: 'var(--elevated)',
                  color: 'var(--accent-alt)',
                  fontFamily: "'JetBrains Mono', monospace"
                }}
                {...props}
              >
                {children}
              </code>
            );
          },
          p({ children }) {
            return <p className="mb-2 text-xs" style={{ color: 'var(--text-primary)', lineHeight: '1.5' }}>{children}</p>;
          },
          h2({ children }) {
            return <h2 className="text-sm font-semibold mb-1 mt-2" style={{ color: 'var(--text-primary)' }}>{children}</h2>;
          },
          h3({ children }) {
            return <h3 className="text-xs font-semibold mb-1 mt-2" style={{ color: 'var(--text-primary)' }}>{children}</h3>;
          },
          ul({ children }) {
            return <ul className="list-disc list-inside pl-2 mb-2 space-y-0.5 text-xs" style={{ color: 'var(--text-primary)' }}>{children}</ul>;
          },
          li({ children }) {
            return <li className="text-xs" style={{ color: 'var(--text-primary)' }}>{children}</li>;
          }
        }}
      >
        {msg.text}
      </ReactMarkdown>
    );
  };

  // Extract node name from label (format: "nodeName\ntype")
  const nodeName = node.label ? node.label.split('\n')[0] : node.id;

  return (
    <div
      className="fixed rounded-lg shadow-lg overflow-hidden"
      style={{
        bottom: '20px',
        right: '20px',
        width: '400px',
        maxHeight: '500px',
        backgroundColor: 'var(--card-bg)',
        border: '1px solid var(--border-default)',
        boxShadow: '0 12px 48px rgba(0, 0, 0, 0.2)',
        zIndex: 1000
      }}
    >
      {/* Header */}
      <div
        className="px-4 py-3 flex justify-between items-center"
        style={{
          backgroundColor: 'var(--elevated)',
          borderBottom: '1px solid var(--border-subtle)'
        }}
      >
        <div className="flex-1">
          <div className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
            📄 {nodeName}
          </div>
          <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            {node.type}
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded transition-colors"
          style={{
            backgroundColor: 'transparent',
            color: 'var(--text-secondary)',
            border: 'none',
            cursor: 'pointer'
          }}
          onMouseEnter={(e) => e.target.style.backgroundColor = 'var(--elevated)'}
          onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Conversation */}
      <div className="overflow-y-auto p-3 space-y-2" style={{ maxHeight: '300px', backgroundColor: 'var(--card-bg)' }}>
        {conversation.length === 0 ? (
          <div className="text-center py-4">
            <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              Ask a question about this code chunk
            </p>
          </div>
        ) : (
          conversation.map((msg, idx) => (
            <div
              key={idx}
              className={`p-2 rounded ${msg.type === 'user' ? 'ml-8' : 'mr-8'}`}
              style={{
                backgroundColor: msg.type === 'user' ? 'var(--elevated)' : 'var(--card-bg)',
                border: msg.type === 'bot' ? '1px solid var(--border-subtle)' : 'none',
                borderLeft: msg.type === 'bot' ? '2px solid var(--accent-alt)' : 'none'
              }}
            >
              {renderMessage(msg)}
            </div>
          ))
        )}
        {isLoading && (
          <div className="flex items-center justify-center py-2">
            <div
              className="animate-spin rounded-full h-4 w-4"
              style={{
                borderWidth: '2px',
                borderStyle: 'solid',
                borderColor: 'var(--border-default)',
                borderTopColor: 'var(--accent)'
              }}
            />
            <span className="ml-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
              Thinking...
            </span>
          </div>
        )}
      </div>

      {/* Input */}
      <div
        className="p-3"
        style={{
          borderTop: '1px solid var(--border-subtle)',
          backgroundColor: 'var(--card-bg)'
        }}
      >
        <div className="flex">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about this code..."
            className="flex-1 px-3 py-2 rounded-l text-sm focus:outline-none transition-all"
            style={{
              backgroundColor: 'var(--input-bg)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-default)',
              fontFamily: "'Inter', sans-serif"
            }}
            onFocus={(e) => e.target.style.borderColor = 'var(--accent)'}
            onBlur={(e) => e.target.style.borderColor = 'var(--border-default)'}
          />
          <button
            onClick={handleSubmit}
            disabled={!query.trim() || isLoading}
            className="px-3 py-2 rounded-r text-sm font-medium transition-all"
            style={{
              backgroundColor: query.trim() && !isLoading ? '#84a07c' : 'var(--border-strong)',
              color: '#ffffff',
              border: 'none',
              cursor: query.trim() && !isLoading ? 'pointer' : 'not-allowed'
            }}
            onMouseEnter={(e) => {
              if (query.trim() && !isLoading) e.target.style.opacity = '0.9';
            }}
            onMouseLeave={(e) => e.target.style.opacity = '1'}
          >
            Ask
          </button>
        </div>
      </div>
    </div>
  );
};

export default NodeChatPanel;
