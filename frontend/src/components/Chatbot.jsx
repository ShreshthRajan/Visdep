import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter';
import { docco } from 'react-syntax-highlighter/dist/esm/styles/hljs';

const ListRenderer = ({ items }) => (
  <ul className="list-disc list-inside pl-4 space-y-1">
    {items.map((item, index) => (
      <li key={index}>{item}</li>
    ))}
  </ul>
);

const Chatbot = () => {
  const [query, setQuery] = useState('');
  const [context, setContext] = useState({});
  const [chatHistory, setChatHistory] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const chatContainerRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    const fetchContext = async () => {
      try {
        const contextResponse = await axios.get('http://localhost:8000/api/context');
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

  const handleQuery = async () => {
    if (!query.trim()) return;

    const currentQuery = query;
    setQuery('');
    setChatHistory(prevHistory => [...prevHistory, { type: 'user', text: currentQuery }]);
    setIsLoading(true);

    try {
      const res = await axios.post('http://localhost:8000/api/query', { query: currentQuery, context });
      setChatHistory(prevHistory => [...prevHistory, { type: 'bot', text: res.data.response }]);
    } catch (error) {
      setChatHistory(prevHistory => [...prevHistory, { type: 'bot', text: 'Error querying Visdep' }]);
      console.error('Error querying Visdep:', error);
    } finally {
      setIsLoading(false);
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
        {isLoading && (
          <div className="flex justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
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