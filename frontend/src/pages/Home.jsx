import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const Home = () => {
  const [repoUrl, setRepoUrl] = useState('');
  const [message, setMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();

  const handleUpload = async () => {
    if (!repoUrl.trim()) return;
    try {
      setIsLoading(true);
      const response = await axios.post('http://localhost:8000/api/upload_repo', { repo_url: repoUrl });
      setMessage(response.data.message);
      setTimeout(() => navigate('/graph-chat'), 2000);
    } catch (error) {
      setMessage('Error uploading repository');
      setIsLoading(false);
    }
  };

  const getRepoName = (url) => {
    const parts = url.split('/');
    return parts[parts.length - 1] || parts[parts.length - 2] || 'repository';
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-50 font-sans">
      <div className="bg-white p-8 rounded-lg shadow-md w-full max-w-md">
        <h1 className="text-4xl font-bold mb-6 text-center text-indigo-700">Visdep</h1>
        {isLoading ? (
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-700 mx-auto mb-4"></div>
            <p className="text-indigo-700 font-medium">Loading {getRepoName(repoUrl)}...</p>
          </div>
        ) : (
          <>
            <input
              type="text"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="Enter GitHub repository URL"
              className="w-full p-3 border border-gray-300 rounded-lg mb-4 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button 
              onClick={handleUpload} 
              className="w-full bg-indigo-600 text-white p-3 rounded-lg hover:bg-indigo-700 transition duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isLoading || !repoUrl.trim()}
            >
              Upload Repository
            </button>
          </>
        )}
        {message && <p className="mt-4 text-center text-red-500">{message}</p>}
      </div>
      <p className="mt-8 text-center text-gray-600">
        Visdep is a tool to visualize and interact with the dependencies in your codebase.
      </p>
    </div>
  );
};

export default Home;