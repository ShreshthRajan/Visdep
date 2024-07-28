import React, { useState } from 'react';
import axios from 'axios';

const FileUploader = () => {
  const [repoUrl, setRepoUrl] = useState('');
  const [message, setMessage] = useState('');

  const handleUpload = async () => {
    try {
      const response = await axios.post('http://localhost:8000/api/upload_repo', { repo_url: repoUrl });
      setMessage(response.data.message);
    } catch (error) {
      setMessage('Error uploading repository');
    }
  };

  return (
    <div>
      <input
        type="text"
        value={repoUrl}
        onChange={(e) => setRepoUrl(e.target.value)}
        placeholder="Enter GitHub repository URL"
      />
      <button onClick={handleUpload}>Upload Repository</button>
      <p>{message}</p>
    </div>
  );
};

export default FileUploader;
