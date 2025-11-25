import React, { memo, useState, useRef, useEffect } from 'react';
import { Handle, Position } from '@xyflow/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import API from '../../api';

/**
 * QueryNode - Interactive node with embedded chat interface
 *
 * Appears under clicked nodes, allows asking questions about that specific code.
 * Can be minimized to a badge on parent node.
 */
const QueryNode = memo(({ id, data }) => {
  const [input, setInput] = useState('');
  const [conversation, setConversation] = useState(data.conversation || []);
  const [isLoading, setIsLoading] = useState(false);
  const [isExpanded, setIsExpanded] = useState(data.isExpanded !== false);
  const inputRef = useRef(null);

  // Auto-focus input when expanded
  useEffect(() => {
    if (isExpanded && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isExpanded]);

  const handleSubmit = async () => {
    if (!input.trim() || isLoading) return;

    const question = input.trim();
    setInput('');

    // Add user message
    const newConversation = [...conversation, { type: 'user', text: question }];
    setConversation(newConversation);
    setIsLoading(true);

    try {
      // Query backend
      const response = await API.post('/api/query', { query: question });
      const answer = response.data.response || response.data;

      // Add bot response
      setConversation([...newConversation, { type: 'bot', text: answer }]);

      // Notify parent to create answer node
      if (data.onAnswer) {
        data.onAnswer(id, question, answer);
      }
    } catch (error) {
      console.error('Query error:', error);
      setConversation([...newConversation, {
        type: 'bot',
        text: 'Error: Could not process query.'
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleMinimize = () => {
    setIsExpanded(false);
    if (data.onMinimize) {
      data.onMinimize(id, conversation);
    }
  };

  const renderMessage = (msg) => {
    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ inline, children }) {
            return inline ? (
              <code style={{
                backgroundColor: '#F0F0F0',
                padding: '2px 4px',
                borderRadius: '3px',
                fontSize: '11px',
                fontFamily: "'JetBrains Mono', monospace",
                color: '#575D90'
              }}>
                {children}
              </code>
            ) : (
              <SyntaxHighlighter
                style={vscDarkPlus}
                customStyle={{
                  fontSize: '10px',
                  padding: '8px',
                  borderRadius: '4px',
                  margin: '4px 0'
                }}
              >
                {String(children)}
              </SyntaxHighlighter>
            );
          },
          p({ children }) {
            return <p style={{ margin: '4px 0', fontSize: '11px', lineHeight: '1.4' }}>{children}</p>;
          }
        }}
      >
        {msg.text}
      </ReactMarkdown>
    );
  };

  if (!isExpanded) {
    // Minimized state - small badge
    return (
      <div
        style={{
          backgroundColor: '#D0D0D0',
          border: '2px solid #999',
          borderRadius: '6px',
          padding: '8px 12px',
          minWidth: '60px',
          cursor: 'pointer',
          fontFamily: "'Inter', sans-serif",
          fontSize: '12px',
          fontWeight: 600,
          color: '#4A4A4A',
          textAlign: 'center'
        }}
        onClick={() => setIsExpanded(true)}
      >
        💬 ①
        <Handle type="target" position={Position.Top} style={{ background: '#999' }} />
      </div>
    );
  }

  return (
    <div
      className="nodrag"
      style={{
        backgroundColor: '#E5E7EB',
        border: '2px solid #9CA3AF',
        borderRadius: '8px',
        padding: '12px',
        minWidth: '320px',
        maxWidth: '380px',
        fontFamily: "'Inter', sans-serif",
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)'
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#9CA3AF' }} />

      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '8px',
        paddingBottom: '8px',
        borderBottom: '1px solid #D1D5DB'
      }}>
        <div style={{ fontSize: '12px', fontWeight: 600, color: '#4A4A4A' }}>
          💬 Query on {data.parentLabel}
        </div>
        <button
          onClick={handleMinimize}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: '16px',
            color: '#6A6A6A',
            padding: '0',
            lineHeight: 1
          }}
          title="Minimize"
        >
          ▼
        </button>
      </div>

      {/* Conversation History */}
      {conversation.length > 0 && (
        <div style={{
          maxHeight: '200px',
          overflowY: 'auto',
          marginBottom: '8px',
          padding: '8px',
          backgroundColor: '#F9FAFB',
          borderRadius: '4px'
        }}>
          {conversation.map((msg, idx) => (
            <div
              key={idx}
              style={{
                marginBottom: '6px',
                padding: '6px',
                backgroundColor: msg.type === 'user' ? '#FFFFFF' : '#F3F4F6',
                borderLeft: msg.type === 'bot' ? '2px solid #575D90' : 'none',
                borderRadius: '4px',
                fontSize: '11px'
              }}
            >
              {renderMessage(msg)}
            </div>
          ))}
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div style={{
          textAlign: 'center',
          padding: '12px',
          color: '#6A6A6A',
          fontSize: '11px'
        }}>
          <div
            className="animate-spin rounded-full h-4 w-4 mx-auto mb-2"
            style={{
              borderWidth: '2px',
              borderStyle: 'solid',
              borderColor: '#D1D5DB',
              borderTopColor: '#84a07c'
            }}
          />
          Processing...
        </div>
      )}

      {/* Input Field */}
      <div style={{ display: 'flex', gap: '6px' }}>
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Ask about this code..."
          className="nodrag"
          style={{
            flex: 1,
            padding: '8px',
            border: '1px solid #D1D5DB',
            borderRadius: '4px',
            fontSize: '12px',
            fontFamily: "'Inter', sans-serif",
            outline: 'none',
            backgroundColor: '#FFFFFF'
          }}
          onFocus={(e) => e.target.style.borderColor = '#84a07c'}
          onBlur={(e) => e.target.style.borderColor = '#D1D5DB'}
        />
        <button
          onClick={handleSubmit}
          disabled={!input.trim() || isLoading}
          className="nodrag"
          style={{
            padding: '8px 16px',
            backgroundColor: input.trim() && !isLoading ? '#84a07c' : '#D1D5DB',
            color: '#FFFFFF',
            border: 'none',
            borderRadius: '4px',
            fontSize: '12px',
            fontWeight: 500,
            cursor: input.trim() && !isLoading ? 'pointer' : 'not-allowed',
            transition: 'opacity 0.2s'
          }}
          onMouseEnter={(e) => {
            if (input.trim() && !isLoading) e.target.style.opacity = '0.9';
          }}
          onMouseLeave={(e) => e.target.style.opacity = '1'}
        >
          Ask
        </button>
      </div>

      <Handle type="source" position={Position.Bottom} style={{ background: '#9CA3AF' }} />
    </div>
  );
});

QueryNode.displayName = 'QueryNode';

export default QueryNode;
