import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

const Chatbot = ({
  isRightPanel,
  onClose,
  onMinimize,
  onSubmit,
  chatHistory = [],
  isLoading = false,
  progressSteps = []
}) => {
  const [query, setQuery] = useState('');
  const chatContainerRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll to bottom when messages update
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [chatHistory, progressSteps]);

  const handleSubmit = (e) => {
    if (e) e.preventDefault();
    if (!query.trim() || isLoading) return;

    onSubmit(query);
    setQuery('');
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
                  backgroundColor: '#2F3840',
                  padding: '12px',
                  borderRadius: '6px',
                  fontSize: '13px',
                  fontFamily: "'JetBrains Mono', monospace",
                  margin: '8px 0',
                  border: 'none'
                }}
                {...props}
              >
                {String(children).replace(/\n$/, '')}
              </SyntaxHighlighter>
            ) : (
              <code
                style={{
                  backgroundColor: 'rgba(132, 160, 124, 0.15)',
                  color: 'var(--accent)',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  fontSize: '13px',
                  fontFamily: "'JetBrains Mono', monospace"
                }}
                {...props}
              >
                {children}
              </code>
            );
          },
          p({ children }) {
            return <p style={{ margin: '0 0 12px 0', lineHeight: '1.7', fontSize: '14px', color: 'var(--text-primary)' }}>{children}</p>;
          },
          h2({ children }) {
            return <h2 style={{ fontSize: '16px', fontWeight: 600, margin: '16px 0 8px 0', color: 'var(--text-primary)' }}>{children}</h2>;
          },
          h3({ children }) {
            return <h3 style={{ fontSize: '14px', fontWeight: 600, margin: '12px 0 6px 0', color: 'var(--text-primary)' }}>{children}</h3>;
          },
          ul({ children }) {
            return <ul style={{ margin: '8px 0', paddingLeft: '20px', lineHeight: '1.6' }}>{children}</ul>;
          },
          ol({ children }) {
            return <ol style={{ margin: '8px 0', paddingLeft: '20px', lineHeight: '1.6' }}>{children}</ol>;
          },
          li({ children }) {
            return <li style={{ margin: '4px 0', fontSize: '14px', color: 'var(--text-primary)' }}>{children}</li>;
          },
          strong({ children }) {
            return <strong style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{children}</strong>;
          },
          a({ href, children }) {
            return <a href={href} style={{ color: 'var(--accent)', textDecoration: 'none' }} target="_blank" rel="noopener noreferrer">{children}</a>;
          },
        }}
      >
        {msg.text}
      </ReactMarkdown>
    );
  };

  // Bottom bar mode (minimal floating input)
  if (!isRightPanel) {
    return (
      <form onSubmit={handleSubmit}>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="px-4 py-2.5 rounded-full focus:outline-none transition-all shadow-lg"
          placeholder="How can I help?"
          style={{
            width: '600px',
            backgroundColor: 'rgba(74, 86, 98, 0.5)',
            color: 'var(--text-primary)',
            border: '1px solid rgba(90, 101, 112, 0.3)',
            fontFamily: "'Inter', sans-serif",
            fontSize: '14px',
            backdropFilter: 'blur(12px)'
          }}
          onFocus={(e) => {
            e.target.style.backgroundColor = 'rgba(74, 86, 98, 0.8)';
            e.target.style.borderColor = 'rgba(132, 160, 124, 0.5)';
          }}
          onBlur={(e) => {
            e.target.style.backgroundColor = 'rgba(74, 86, 98, 0.5)';
            e.target.style.borderColor = 'rgba(90, 101, 112, 0.3)';
          }}
        />
      </form>
    );
  }

  // Floating panel mode (enterprise-grade minimal design)
  return (
    <div className="flex flex-col h-full" style={{ backgroundColor: '#424D57' }}>
      {/* Minimal draggable header */}
      <div
        className="chat-drag-handle flex items-center justify-between px-3 py-2 cursor-move"
        style={{
          borderBottom: '1px solid rgba(90, 101, 112, 0.3)',
          backgroundColor: 'rgba(83, 95, 107, 0.4)'
        }}
      >
        <div style={{
          width: '24px',
          height: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '3px',
          opacity: 0.4
        }}>
          <div style={{ width: '100%', height: '2px', backgroundColor: 'var(--text-secondary)', borderRadius: '1px' }} />
          <div style={{ width: '100%', height: '2px', backgroundColor: 'var(--text-secondary)', borderRadius: '1px' }} />
          <div style={{ width: '100%', height: '2px', backgroundColor: 'var(--text-secondary)', borderRadius: '1px' }} />
        </div>
        <div className="flex gap-2">
          {onMinimize && (
            <button
              onClick={onMinimize}
              className="p-1 rounded transition-opacity hover:opacity-70"
              style={{ color: 'var(--text-secondary)', background: 'none', border: 'none', cursor: 'pointer' }}
              title="Minimize"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
          )}
          {onClose && (
            <button
              onClick={onClose}
              className="p-1 rounded transition-opacity hover:opacity-70"
              style={{ color: 'var(--text-secondary)', background: 'none', border: 'none', cursor: 'pointer' }}
              title="Close"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Messages area */}
      <div
        ref={chatContainerRef}
        className="flex-1 overflow-y-auto px-4 py-6"
        style={{ backgroundColor: '#424D57' }}
      >
        {chatHistory.length === 0 && !isLoading && (
          <div className="flex items-center justify-center h-full">
            <p style={{
              fontSize: '13px',
              color: 'rgba(184, 197, 208, 0.4)',
              fontFamily: "'Inter', sans-serif"
            }}>
              Ask a question to get started
            </p>
          </div>
        )}

        {chatHistory.map((msg, index) => (
          <div
            key={index}
            style={{
              display: 'flex',
              justifyContent: msg.type === 'user' ? 'flex-end' : 'flex-start',
              marginBottom: '20px'
            }}
          >
            <div
              style={{
                maxWidth: '90%',
                padding: msg.type === 'user' ? '6px 12px' : '0',
                backgroundColor: msg.type === 'user' ? 'rgba(83, 95, 107, 0.6)' : 'transparent',
                borderLeft: msg.type === 'bot' ? '2px solid var(--accent)' : 'none',
                paddingLeft: msg.type === 'bot' ? '12px' : '12px',
                borderRadius: msg.type === 'user' ? '8px' : '0'
              }}
            >
              {renderMessage(msg)}
            </div>
          </div>
        ))}

        {/* Minimal progress indicator */}
        {isLoading && progressSteps.length > 0 && (
          <div style={{ padding: '12px 0' }}>
            {progressSteps
              .filter(step => step.status === 'active')
              .map(step => (
                <div key={step.id} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div
                    className="animate-pulse"
                    style={{
                      width: '4px',
                      height: '4px',
                      borderRadius: '50%',
                      backgroundColor: 'var(--accent)'
                    }}
                  />
                  <span style={{
                    fontSize: '12px',
                    color: 'var(--text-secondary)',
                    fontFamily: "'Inter', sans-serif"
                  }}>
                    {step.message}
                  </span>
                </div>
              ))}
          </div>
        )}
      </div>

      {/* Input area */}
      <div
        className="px-3 py-3"
        style={{
          borderTop: '1px solid rgba(90, 101, 112, 0.3)',
          backgroundColor: '#424D57'
        }}
      >
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            className="flex-1 px-3 py-2 rounded-lg focus:outline-none transition-all text-sm"
            placeholder={isLoading ? "Processing..." : "Ask a follow-up..."}
            style={{
              backgroundColor: 'rgba(61, 72, 80, 0.6)',
              color: 'var(--text-primary)',
              border: '1px solid rgba(90, 101, 112, 0.3)',
              fontFamily: "'Inter', sans-serif",
              opacity: isLoading ? 0.5 : 1
            }}
            onFocus={(e) => {
              e.target.style.backgroundColor = 'rgba(61, 72, 80, 0.9)';
              e.target.style.borderColor = 'var(--accent)';
            }}
            onBlur={(e) => {
              e.target.style.backgroundColor = 'rgba(61, 72, 80, 0.6)';
              e.target.style.borderColor = 'rgba(90, 101, 112, 0.3)';
            }}
          />
          <button
            type="submit"
            disabled={isLoading || !query.trim()}
            className="px-3 py-2 text-sm font-medium rounded-lg transition-all disabled:opacity-30 disabled:cursor-not-allowed"
            style={{
              backgroundColor: 'var(--accent)',
              color: '#FFFFFF',
              border: 'none',
              cursor: (isLoading || !query.trim()) ? 'not-allowed' : 'pointer',
              fontFamily: "'Inter', sans-serif"
            }}
            onMouseEnter={(e) => {
              if (!isLoading && query.trim()) e.target.style.opacity = '0.85';
            }}
            onMouseLeave={(e) => e.target.style.opacity = '1'}
          >
            Ask
          </button>
        </form>
      </div>
    </div>
  );
};

export default Chatbot;
