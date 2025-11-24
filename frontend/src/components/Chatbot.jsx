import React, { useState, useEffect, useRef } from 'react';
import API from '../api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

const Chatbot = ({ onHighlightNodes, nodeQuery, onQueryProcessed }) => {
  const [query, setQuery] = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [progressSteps, setProgressSteps] = useState([]);
  const chatContainerRef = useRef(null);
  const textareaRef = useRef(null);

  // Node queries are now handled by inline panel, not main chat
  // This effect is disabled - inline node chat panel handles node-specific queries

  // ENTERPRISE FIX: Removed context fetching - backend loads from DB server-side
  // Benefits:
  // 1. Eliminates race condition (no timing dependency)
  // 2. Reduces network traffic (no 3MB+ JSON transfer)
  // 3. Faster queries (backend has direct DB access)
  // 4. More secure (backend controls data source)

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [chatHistory]);

  // Smart progress generator - creates contextual chain-of-thought steps
  const generateSmartProgress = (queryText) => {
    // Extract keywords from query (functions, classes, concepts)
    const keywords = queryText
      .replace(/[?.,]/g, '')
      .split(' ')
      .filter(word =>
        word.length > 3 &&
        !['does', 'what', 'how', 'why', 'when', 'where', 'the', 'this', 'that', 'with', 'from', 'into'].includes(word.toLowerCase())
      )
      .slice(0, 3);

    // Generate intelligent progress steps
    const steps = [
      {
        id: 1,
        icon: '🔍',
        message: `Searching codebase for "${keywords[0] || 'relevant code'}"...`,
        timing: 0,
        status: 'active'
      },
      {
        id: 2,
        icon: '🧠',
        message: 'Running semantic analysis across codebase...',
        timing: 2000,
        status: 'pending'
      },
      {
        id: 3,
        icon: '📊',
        message: keywords[1] ? `Analyzing ${keywords[1]} implementation patterns...` : 'Analyzing implementation patterns...',
        timing: 5000,
        status: 'pending'
      },
      {
        id: 4,
        icon: '🔗',
        message: 'Expanding dependency graph (3-hop traversal)...',
        timing: 8000,
        status: 'pending'
      },
      {
        id: 5,
        icon: '🤖',
        message: `Synthesizing answer about ${keywords[2] || 'your question'}...`,
        timing: 12000,
        status: 'pending'
      },
      {
        id: 6,
        icon: '✨',
        message: 'Generating citations and highlighting code...',
        timing: 18000,
        status: 'pending'
      }
    ];

    return steps;
  };

  const handleQuery = async () => {
    if (!query.trim()) return;

    const currentQuery = query;
    setQuery('');
    setChatHistory(prevHistory => [...prevHistory, { type: 'user', text: currentQuery }]);
    setIsLoading(true);

    // Generate smart progress steps
    const steps = generateSmartProgress(currentQuery);
    setProgressSteps(steps);

    // Animate progress steps
    steps.forEach((step, index) => {
      setTimeout(() => {
        setProgressSteps(prev =>
          prev.map(s =>
            s.id === step.id ? { ...s, status: 'active' } :
            s.id < step.id ? { ...s, status: 'complete' } : s
          )
        );
      }, step.timing);
    });

    try {
      console.log('🔍 CHATBOT DEBUG: Sending query:', currentQuery);
      // ENTERPRISE FIX: Backend loads chunks from database server-side
      // No need to send 3MB+ context over network (faster, more robust)
      const res = await API.post('/api/query', { query: currentQuery });

      console.log('📦 CHATBOT DEBUG: Received response:', {
        hasResponse: !!res.data.response,
        hasCitations: !!res.data.citations,
        hasHighlightedNodes: !!res.data.highlighted_nodes,
        citationCount: res.data.citations?.length || 0,
        highlightedNodeCount: res.data.highlighted_nodes?.length || 0
      });

      // Extract response text (handle both formats)
      const responseText = res.data.response || res.data;
      setChatHistory(prevHistory => [...prevHistory, { type: 'bot', text: responseText }]);

      // Highlight graph nodes if citations are present
      if (res.data.highlighted_nodes && onHighlightNodes) {
        console.log('✅ CHATBOT: Calling onHighlightNodes with:', res.data.highlighted_nodes);
        onHighlightNodes(res.data.highlighted_nodes);
      } else if (!res.data.highlighted_nodes) {
        console.warn('⚠️ CHATBOT: No highlighted_nodes in response');
      } else if (!onHighlightNodes) {
        console.warn('⚠️ CHATBOT: onHighlightNodes callback is undefined');
      }

      // Log full response for debugging
      if (res.data.citations && res.data.citations.length > 0) {
        console.log('📑 CHATBOT: Citations:', res.data.citations);
      }
    } catch (error) {
      // ENTERPRISE ERROR HANDLING: Provide specific, actionable error messages
      let errorMessage = 'Error querying Visdep';

      if (error.response?.status === 400) {
        // Bad request - likely no repo loaded
        errorMessage = error.response.data?.detail || 'Please upload a repository first before asking questions.';
      } else if (error.response?.status === 500) {
        // Server error
        errorMessage = 'Server error. Please try again or contact support if the issue persists.';
      } else if (error.message) {
        errorMessage = `Error: ${error.message}`;
      }

      setChatHistory(prevHistory => [...prevHistory, { type: 'bot', text: errorMessage }]);
      console.error('❌ CHATBOT ERROR:', error);
      console.error('Error details:', error.response?.data);
    } finally {
      setIsLoading(false);
      setProgressSteps([]); // Clear progress after completion
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleQuery();
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
                  padding: '1rem',
                  borderRadius: '0.5rem',
                  fontSize: '0.875rem',
                  fontFamily: "'JetBrains Mono', monospace",
                  margin: '0.5rem 0',
                  border: '1px solid var(--border-default)'
                }}
                {...props}
              >
                {String(children).replace(/\n$/, '')}
              </SyntaxHighlighter>
            ) : (
              <code
                className="px-1.5 py-0.5 rounded text-sm"
                style={{
                  backgroundColor: 'var(--elevated)',
                  color: 'var(--accent)',
                  fontFamily: "'JetBrains Mono', monospace"
                }}
                {...props}
              >
                {children}
              </code>
            );
          },
          p({ children }) {
            return <p className="mb-3" style={{ color: 'var(--text-primary)', lineHeight: '1.6' }}>{children}</p>;
          },
          h1({ children }) {
            return <h1 className="text-2xl font-bold mb-3" style={{ color: 'var(--text-primary)' }}>{children}</h1>;
          },
          h2({ children }) {
            return <h2 className="text-xl font-semibold mb-2 mt-4" style={{ color: 'var(--text-primary)' }}>{children}</h2>;
          },
          h3({ children }) {
            return <h3 className="text-lg font-semibold mb-2 mt-3" style={{ color: 'var(--text-primary)' }}>{children}</h3>;
          },
          ul({ children }) {
            return <ul className="list-disc list-inside pl-4 mb-3 space-y-1" style={{ color: 'var(--text-primary)' }}>{children}</ul>;
          },
          ol({ children }) {
            return <ol className="list-decimal list-inside pl-4 mb-3 space-y-1" style={{ color: 'var(--text-primary)' }}>{children}</ol>;
          },
          li({ children }) {
            return <li className="mb-1" style={{ color: 'var(--text-primary)' }}>{children}</li>;
          },
          strong({ children }) {
            return <strong className="font-semibold" style={{ color: 'var(--text-primary)' }}>{children}</strong>;
          },
          em({ children }) {
            return <em className="italic" style={{ color: 'var(--text-secondary)' }}>{children}</em>;
          },
          a({ href, children }) {
            return <a href={href} className="underline" style={{ color: 'var(--accent)' }} target="_blank" rel="noopener noreferrer">{children}</a>;
          },
          blockquote({ children }) {
            return (
              <blockquote
                className="pl-4 my-3"
                style={{
                  borderLeft: '3px solid var(--class)',
                  color: 'var(--text-secondary)',
                  fontStyle: 'italic'
                }}
              >
                {children}
              </blockquote>
            );
          }
        }}
      >
        {msg.text}
      </ReactMarkdown>
    );
  };

  return (
    <div className="flex flex-col h-full" style={{ backgroundColor: 'var(--near-black)' }}>
      <div ref={chatContainerRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {chatHistory.map((msg, index) => (
          <div key={index} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className="max-w-xs lg:max-w-2xl px-4 py-3 rounded-lg"
              style={{
                backgroundColor: msg.type === 'user' ? 'var(--elevated)' : 'var(--card-bg)',
                color: 'var(--text-primary)',
                border: msg.type === 'bot' ? '1px solid var(--border-default)' : 'none',
                borderLeft: msg.type === 'bot' ? '3px solid var(--accent-alt)' : 'none',
                boxShadow: msg.type === 'bot' ? '0 2px 8px rgba(0, 0, 0, 0.1)' : 'none'
              }}
            >
              {renderMessage(msg)}
            </div>
          </div>
        ))}
        {/* Smart Chain-of-Thought Progress */}
        {isLoading && progressSteps.length > 0 && (
          <div
            className="border rounded-lg p-4 shadow-lg"
            style={{
              backgroundColor: 'var(--card-bg)',
              borderColor: 'var(--function)',
              borderWidth: '1px'
            }}
          >
            <div className="space-y-3">
              {progressSteps.map((step) => (
                <div key={step.id} className="flex items-start space-x-3">
                  <span className={`text-2xl transition-all duration-300 ${
                    step.status === 'complete' ? 'opacity-50 scale-90' :
                    step.status === 'active' ? 'opacity-100 scale-110 animate-pulse' :
                    'opacity-30'
                  }`}>
                    {step.status === 'complete' ? '✓' : step.icon}
                  </span>
                  <div className="flex-1">
                    <p className="text-sm transition-all duration-300" style={{
                      color: step.status === 'complete' ? 'var(--text-secondary)' :
                             step.status === 'active' ? 'var(--accent)' :
                             'var(--text-tertiary)',
                      textDecoration: step.status === 'complete' ? 'line-through' : 'none',
                      fontWeight: step.status === 'active' ? 600 : 400
                    }}>
                      {step.message}
                    </p>
                    {step.status === 'active' && (
                      <div className="mt-1 h-1 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--border-default)' }}>
                        <div className="h-full rounded-full animate-progress" style={{
                          width: '100%',
                          backgroundColor: 'var(--accent)'
                        }}></div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      <div className="p-4" style={{ borderTop: '1px solid var(--border-subtle)', backgroundColor: 'var(--near-black)' }}>
        <div className="flex rounded-md shadow-sm">
          <textarea
            ref={textareaRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 px-4 py-2 rounded-l-md resize-none focus:outline-none transition-all"
            placeholder="Ask about the codebase... (Shift+Enter for new line)"
            rows="1"
            style={{
              minHeight: '40px',
              maxHeight: '120px',
              backgroundColor: 'var(--input-bg)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-default)',
              fontFamily: "'Inter', sans-serif"
            }}
            onFocus={(e) => e.target.style.borderColor = 'var(--accent)'}
            onBlur={(e) => e.target.style.borderColor = 'var(--border-default)'}
          />
          <button
            onClick={handleQuery}
            className="px-4 py-2 font-medium rounded-r-md focus:outline-none transition-all"
            style={{
              backgroundColor: '#84a07c',
              color: '#ffffff',
              border: 'none',
              cursor: 'pointer'
            }}
            onMouseEnter={(e) => e.target.style.opacity = '0.9'}
            onMouseLeave={(e) => e.target.style.opacity = '1'}
          >
            Ask
          </button>
        </div>
      </div>
    </div>
  );
};

export default Chatbot;