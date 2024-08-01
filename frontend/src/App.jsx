// dependency_extraction/frontend/src/App.jsx
import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import Home from './pages/Home';
import FileUploader from './components/FileUploader';
import GraphChat from './pages/GraphChat'; // New combined graph and chat page

const App = () => (
  <Router>
    <Navbar />
    <div className="container mx-auto p-4">
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/upload" element={<FileUploader />} />
        <Route path="/graph-chat" element={<GraphChat />} />
      </Routes>
    </div>
  </Router>
);

export default App;
