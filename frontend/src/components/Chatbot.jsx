import React, { useState } from 'react';
import axios from 'axios';

const Chatbot = () => {
  const [query, setQuery] = useState('');
  const [response, setResponse] = useState('');

  const handleQuery = async () => {
    try {
      const res = await axios.post('http://localhost:8000/api/query', { query, context: '{}' });
      setResponse(res.data.response);
    } catch (error) {
      setResponse('Error querying Jamba');
      console.error('Error querying Jamba:', error);
    }
  };

  return (
    <div>
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Ask a question about the codebase"
      />
      <button onClick={handleQuery}>Ask</button>
      <p>{response}</p>
    </div>
  );
};

export default Chatbot;
