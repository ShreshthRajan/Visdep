import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import Home from './pages/Home';
import FileUploader from './components/FileUploader';
import Chatbot from './components/Chatbot';
import GraphView from './pages/GraphView';

const App = () => (
  <Router>
    <Navbar />
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/upload" element={<FileUploader />} />
      <Route path="/chat" element={<Chatbot />} />
      <Route path="/graph" element={<GraphView />} />
    </Routes>
  </Router>
);

export default App;
