// frontend/src/components/Chatbot.jsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';

const Chatbot = () => {
  const [query, setQuery] = useState('');
  const [context, setContext] = useState({});
  const [chatHistory, setChatHistory] = useState([]);

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

  const handleQuery = async () => {
    try {
      const res = await axios.post('http://localhost:8000/api/query', { query, context });
      setChatHistory([...chatHistory, { type: 'user', text: query }, { type: 'bot', text: res.data.response }]);
      setQuery('');
    } catch (error) {
      setChatHistory([...chatHistory, { type: 'user', text: query }, { type: 'bot', text: 'Error querying Jamba' }]);
      console.error('Error querying Jamba:', error);
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-50 rounded-lg shadow-md p-4">
      <div className="flex-1 overflow-y-auto mb-4 p-4 border border-gray-200 rounded bg-white">
        {chatHistory.map((msg, index) => (
          <div key={index} className={`mb-3 ${msg.type === 'user' ? 'text-right' : 'text-left'}`}>
            <p className={`inline-block p-2 rounded-lg ${msg.type === 'user' ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-800'}`}>
              {msg.text}
            </p>
          </div>
        ))}
      </div>
      <div className="flex">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask a question about the codebase"
          className="flex-1 p-2 border border-gray-300 rounded-l-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button onClick={handleQuery} className="bg-blue-600 text-white p-2 rounded-r-lg hover:bg-blue-700 transition duration-200">Ask</button>
      </div>
    </div>
  );
};

export default Chatbot;