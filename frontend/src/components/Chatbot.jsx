import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const Chatbot = () => {
  const [query, setQuery] = useState('');
  const [context, setContext] = useState({});
  const [chatHistory, setChatHistory] = useState([]);
  const chatContainerRef = useRef(null);

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

    try {
      const res = await axios.post('http://localhost:8000/api/query', { query, context });
      setChatHistory([...chatHistory, { type: 'user', text: query }, { type: 'bot', text: res.data.response }]);
      setQuery('');
    } catch (error) {
      setChatHistory([...chatHistory, { type: 'user', text: query }, { type: 'bot', text: 'Error querying Visdep' }]);
      console.error('Error querying Visdep:', error);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div ref={chatContainerRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {chatHistory.map((msg, index) => (
          <div key={index} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${msg.type === 'user' ? 'bg-indigo-500 text-white' : 'bg-gray-200 text-gray-800'}`}>
              {msg.text}
            </div>
          </div>
        ))}
      </div>
      <div className="border-t p-4">
        <div className="flex rounded-md shadow-sm">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleQuery()}
            className="flex-1 px-4 py-2 border-gray-300 rounded-l-md focus:ring-indigo-500 focus:border-indigo-500"
            placeholder="Ask about the codebase..."
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