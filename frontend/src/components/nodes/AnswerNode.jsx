import React, { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

/**
 * AnswerNode - Displays AI responses under query nodes
 */
const AnswerNode = memo(({ data }) => {
  const { question, answer } = data;

  const renderMarkdown = (text) => {
    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ inline, children }) {
            return inline ? (
              <code style={{
                backgroundColor: '#E0E0E0',
                padding: '2px 4px',
                borderRadius: '3px',
                fontSize: '10px',
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
                  margin: '4px 0',
                  maxHeight: '150px',
                  overflow: 'auto'
                }}
              >
                {String(children)}
              </SyntaxHighlighter>
            );
          },
          p({ children }) {
            return <p style={{ margin: '4px 0', fontSize: '11px', lineHeight: '1.4', color: '#1A1A1A' }}>{children}</p>;
          },
          h2({ children }) {
            return <h2 style={{ fontSize: '12px', fontWeight: 600, margin: '8px 0 4px', color: '#1A1A1A' }}>{children}</h2>;
          },
          ul({ children }) {
            return <ul style={{ marginLeft: '16px', fontSize: '11px', color: '#1A1A1A' }}>{children}</ul>;
          }
        }}
      >
        {text}
      </ReactMarkdown>
    );
  };

  return (
    <div
      style={{
        backgroundColor: '#F9FAFB',
        border: '2px solid #D1D5DB',
        borderLeft: '3px solid #575D90',
        borderRadius: '8px',
        padding: '12px',
        minWidth: '300px',
        maxWidth: '400px',
        maxHeight: '300px',
        overflow: 'auto',
        fontFamily: "'Inter', sans-serif",
        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)'
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#D1D5DB' }} />

      {/* Question */}
      <div style={{
        fontSize: '11px',
        fontWeight: 600,
        color: '#4A4A4A',
        marginBottom: '8px',
        fontStyle: 'italic'
      }}>
        Q: {question}
      </div>

      {/* Answer */}
      <div style={{ fontSize: '11px', color: '#1A1A1A' }}>
        {renderMarkdown(answer)}
      </div>

      <Handle type="source" position={Position.Bottom} style={{ background: '#D1D5DB' }} />
    </div>
  );
});

AnswerNode.displayName = 'AnswerNode';

export default AnswerNode;
