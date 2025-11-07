import React, { useState, useEffect, useRef } from 'react';
import API from '../api';
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter';
import { docco } from 'react-syntax-highlighter/dist/esm/styles/hljs';

const ListRenderer = ({ items }) => (
  <ul className="list-disc list-inside pl-4 space-y-1">
    {items.map((item, index) => (
      <li key={index}>{item}</li>
    ))}
  </ul>
);

const Chatbot = ({ onHighlightNodes }) => {
  const [query, setQuery] = useState('');
  const [context, setContext] = useState({});
  const [chatHistory, setChatHistory] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [progressSteps, setProgressSteps] = useState([]);
  const chatContainerRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    const fetchContext = async () => {
      try {
        const contextResponse = await API.get('/api/context');
        setContext(contextResponse.data);
      } catch (error) {
        console.error('Error fetching context:', error);
      }
    };
    fetchContext();
  }, []);

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

    const repoName = context.repo_name || 'repository';
    const chunkCount = Object.keys(context).length;

    // Generate intelligent progress steps
    const steps = [
      {
        id: 1,
        icon: '🔍',
        message: `Searching ${chunkCount} code chunks for "${keywords[0] || 'relevant code'}"...`,
        timing: 0,
        status: 'active'
      },
      {
        id: 2,
        icon: '🧠',
        message: `Running semantic analysis across ${repoName} codebase...`,
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
      const res = await API.post('/api/query', { query: currentQuery, context });

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
      setChatHistory(prevHistory => [...prevHistory, { type: 'bot', text: 'Error querying Visdep' }]);
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
    const lines = msg.text.split('\n');
    return lines.map((line, index) => {
      if (line.startsWith('```')) {
        const code = lines.slice(index + 1, lines.findIndex((l, i) => i > index && l.startsWith('```'))).join('\n');
        return (
          <SyntaxHighlighter language="javascript" style={docco} className="rounded-md my-2">
            {code}
          </SyntaxHighlighter>
        );
      } else if (line.match(/^\d+\.\s/)) {
        const listItems = lines.filter(l => l.match(/^\d+\.\s/)).map(l => l.replace(/^\d+\.\s/, ''));
        return <ListRenderer items={listItems} />;
      } else {
        return <p className="mb-2">{line}</p>;
      }
    });
  };

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <div ref={chatContainerRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {chatHistory.map((msg, index) => (
          <div key={index} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-xs lg:max-w-2xl px-4 py-2 rounded-lg ${
              msg.type === 'user' ? 'bg-indigo-500 text-white' : 'bg-white text-gray-800 shadow-md'
            }`}>
              {renderMessage(msg)}
            </div>
          </div>
        ))}
        {/* Smart Chain-of-Thought Progress */}
        {isLoading && progressSteps.length > 0 && (
          <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-indigo-200 rounded-lg p-4 shadow-lg">
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
                    <p className={`text-sm transition-all duration-300 ${
                      step.status === 'complete' ? 'text-gray-500 line-through' :
                      step.status === 'active' ? 'text-indigo-700 font-semibold' :
                      'text-gray-400'
                    }`}>
                      {step.message}
                    </p>
                    {step.status === 'active' && (
                      <div className="mt-1 h-1 bg-indigo-200 rounded-full overflow-hidden">
                        <div className="h-full bg-indigo-600 rounded-full animate-progress" style={{width: '100%'}}></div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      <div className="border-t p-4 bg-white">
        <div className="flex rounded-md shadow-sm">
          <textarea
            ref={textareaRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1 px-4 py-2 border-gray-300 rounded-l-md focus:ring-indigo-500 focus:border-indigo-500 resize-none"
            placeholder="Ask about the codebase... (Shift+Enter for new line)"
            rows="1"
            style={{ minHeight: '40px', maxHeight: '120px' }}
          />
          <button
            onClick={handleQuery}
            className="px-4 py-2 bg-indigo-600 text-white font-medium rounded-r-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
          >
            Ask
          </button>
        </div>
      </div>
    </div>
  );
};

export default Chatbot;