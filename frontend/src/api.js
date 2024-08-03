// frontend/src/api.js
import axios from 'axios';

const API = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:8000',
});

export const uploadRepo = (repoUrl) => API.post('/api/upload_repo', { repo_url: repoUrl });
export const queryChatbot = (query, context) => API.post('/api/chat', { query, context });
export const fetchContext = () => API.get('/api/context');

export default API;
