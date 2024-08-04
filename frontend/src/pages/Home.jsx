// frontend/src/pages/Home.jsx
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';


const Home = () => {
  const [repoUrl, setRepoUrl] = useState('');
  const [message, setMessage] = useState('');
  const navigate = useNavigate();

  const handleUpload = async () => {
    try {
      const response = await axios.post('http://localhost:8000/api/upload_repo', { repo_url: repoUrl });
      setMessage(response.data.message);
      navigate('/graph-chat');
    } catch (error) {
      setMessage('Error uploading repository');
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
      <div className="bg-white p-8 rounded-lg shadow-md w-full max-w-md">
        <h1 className="text-4xl font-bold mb-6 text-center text-blue-600">Visdep</h1>
        <input
          type="text"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          placeholder="Enter GitHub repository URL"
          className="w-full p-3 border border-gray-300 rounded-lg mb-4 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button 
          onClick={handleUpload} 
          className="w-full bg-blue-600 text-white p-3 rounded-lg hover:bg-blue-700 transition duration-200"
        >
          Upload Repository
        </button>
        {message && <p className="mt-4 text-center text-red-500">{message}</p>}
      </div>
      <p className="mt-8 text-center text-gray-600">
        Visdep is a tool to visualize and interact with the dependencies in your codebase.
      </p>
    </div>
  );
};

export default Home;
