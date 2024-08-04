// // frontend/src/components/fileuploader.jsx
// import React, { useState } from 'react';
// import axios from 'axios';
// import { useNavigate } from 'react-router-dom';

// const FileUploader = () => {
//   const [repoUrl, setRepoUrl] = useState('');
//   const [message, setMessage] = useState('');
//   const navigate = useNavigate();

//   const handleUpload = async () => {
//     try {
//       const response = await axios.post('http://localhost:8000/api/upload_repo', { repo_url: repoUrl });
//       setMessage(response.data.message);
//       navigate('/graph-chat');
//     } catch (error) {
//       setMessage('Error uploading repository');
//     }
//   };

//   return (
//     <div className="max-w-lg mx-auto mt-10">
//       <input
//         type="text"
//         value={repoUrl}
//         onChange={(e) => setRepoUrl(e.target.value)}
//         placeholder="Enter GitHub repository URL"
//         className="w-full p-2 border border-gray-300 rounded mb-4"
//       />
//       <button onClick={handleUpload} className="w-full bg-blue-600 text-white p-2 rounded">Upload Repository</button>
//       <p className="mt-4 text-center">{message}</p>
//     </div>
//   );
// };

// export default FileUploader;
