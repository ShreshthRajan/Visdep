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
    <div className="flex flex-col items-center justify-center h-screen bg-white">
      <h1 className="text-5xl font-bold mb-8">Visdep</h1>
      <input
        type="text"
        value={repoUrl}
        onChange={(e) => setRepoUrl(e.target.value)}
        placeholder="Enter GitHub repository URL"
        className="w-1/3 p-2 border border-gray-300 rounded mb-4"
      />
      <button onClick={handleUpload} className="bg-blue-600 text-white p-2 rounded">Upload Repository</button>
      <p className="mt-4 text-center text-gray-500">{message}</p>
      <p className="absolute bottom-5 left-5 text-gray-500">Visdep is a tool to visualize and interact with the dependencies in your codebase.</p>
    </div>
  );
};

export default Home;
