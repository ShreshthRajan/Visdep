import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

const Chatbot = ({ onSubmit, chatHistory = [], isLoading = false, progressSteps = [], contextNode = null }) => {
  const [query, setQuery] = useState('');
  const chatContainerRef = useRef(null);
  const inputRef = useRef(null);

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
    if (e.key === 'Enter') {
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
            return !inline ? (
              <SyntaxHighlighter
                style={vscDarkPlus}
                language={match ? match[1] : 'python'}
                PreTag="div"
                customStyle={{
                  backgroundColor: '#000000',  // Pure black for depth
                  padding: '12px',
                  borderRadius: '4px',
                  fontSize: '11px',
                  fontFamily: "'JetBrains Mono', monospace",
                  margin: '8px 0 8px 12px',
                  border: '1px solid rgba(59, 130, 246, 0.15)'  // Subtle blue border
                }}
                {...props}
              >
                {String(children).replace(/\n$/, '')}
              </SyntaxHighlighter>
            ) : (
              <code
                style={{
                  backgroundColor: 'rgba(59, 130, 246, 0.15)',
                  color: '#3b82f6',
                  padding: '2px 4px',
                  borderRadius: '3px',
                  fontSize: '11px',
                  fontFamily: "'JetBrains Mono', monospace"
                }}
                {...props}
              >
                {children}
              </code>
            );
          },
          p: ({ children }) => <p style={{ margin: '0 0 8px 0', lineHeight: '1.5', fontSize: '13px', color: '#f4f4f5' }}>{children}</p>,
          h2: ({ children }) => <h2 style={{ fontSize: '14px', fontWeight: 600, margin: '12px 0 6px 0', color: '#f4f4f5' }}>{children}</h2>,
          ul: ({ children }) => <ul style={{ margin: '6px 0 6px 12px', paddingLeft: '16px', lineHeight: '1.5' }}>{children}</ul>,
          li: ({ children }) => <li style={{ margin: '3px 0', fontSize: '13px', color: '#f4f4f5' }}>{children}</li>,
          strong: ({ children }) => <strong style={{ fontWeight: 600, color: '#f4f4f5' }}>{children}</strong>,
          a: ({ href, children }) => <a href={href} style={{ color: '#3b82f6', textDecoration: 'none' }} target="_blank" rel="noopener noreferrer">{children}</a>,
        }}
      >
        {msg.text}
      </ReactMarkdown>
    );
  };

  return (
    <div className="flex flex-col h-full" style={{ backgroundColor: '#050505' }}>
      {/* Messages - Flat Stream */}
      <div
        ref={chatContainerRef}
        className="flex-1 overflow-y-auto px-4 py-6"
        style={{ backgroundColor: '#050505' }}
      >
        {chatHistory.length === 0 && !isLoading && (
          <div className="flex items-center justify-center h-full">
            <p style={{ fontSize: '13px', color: '#71717a', fontFamily: "'Inter', sans-serif" }}>
              Ask a question to get started
            </p>
          </div>
        )}

        {chatHistory.map((msg, index) => (
          <div
            key={index}
            style={{
              marginBottom: '16px',
              paddingLeft: msg.type === 'bot' ? '12px' : '0',
              borderLeft: msg.type === 'bot' ? '2px solid rgba(59, 130, 246, 0.3)' : 'none'
            }}
          >
            {/* Label */}
            <div style={{
              fontSize: '10px',
              color: '#71717a',
              marginBottom: '4px',
              fontFamily: "'Inter', sans-serif",
              textTransform: 'uppercase',
              letterSpacing: '0.5px'
            }}>
              {msg.type === 'user' ? 'You' : 'Agent'}
            </div>
            {/* Message */}
            <div style={{
              fontSize: '13px',
              lineHeight: '1.5',
              color: '#f4f4f5'
            }}>
              {renderMessage(msg)}
            </div>
          </div>
        ))}

        {/* Progress */}
        {isLoading && progressSteps.length > 0 && (
          <div style={{ padding: '12px 0', marginLeft: '12px', borderLeft: '2px solid rgba(59, 130, 246, 0.3)' }}>
            <div style={{ fontSize: '10px', color: '#71717a', marginBottom: '4px', marginLeft: '12px', textTransform: 'uppercase' }}>
              Agent
            </div>
            {progressSteps
              .filter(step => step.status === 'active')
              .map(step => (
                <div key={step.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginLeft: '12px' }}>
                  <div
                    className="animate-pulse"
                    style={{
                      width: '3px',
                      height: '3px',
                      borderRadius: '50%',
                      backgroundColor: '#3b82f6'
                    }}
                  />
                  <span style={{
                    fontSize: '12px',
                    color: '#a1a1aa',
                    fontFamily: "'Inter', sans-serif"
                  }}>
                    {step.message}
                  </span>
                </div>
              ))}
          </div>
        )}
      </div>

      {/* Terminal-Style Input */}
      <div
        className="px-4 py-3"
        style={{
          borderTop: '1px solid rgba(255, 255, 255, 0.05)',
          backgroundColor: '#050505'
        }}
      >
        <div className="flex items-center gap-2">
          <span style={{ color: '#3b82f6', fontSize: '14px', fontFamily: "'JetBrains Mono', monospace" }}>&gt;</span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            placeholder={contextNode ? `Ask about ${contextNode}` : 'Ask the codebase'}
            className="flex-1 px-0 py-1 text-sm focus:outline-none transition-all bg-transparent"
            style={{
              color: '#f4f4f5',
              border: 'none',
              fontFamily: "'Inter', sans-serif",
              opacity: isLoading ? 0.5 : 1,
              caretColor: '#3b82f6'
            }}
          />
        </div>
      </div>
    </div>
  );
};

export default Chatbot;
