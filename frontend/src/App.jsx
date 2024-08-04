// frontend/src/App.jsx
import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import GraphChat from './pages/GraphChat';

const App = () => (
  <Router>
    <div className="container mx-auto p-4">
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/graph-chat" element={<GraphChat />} />
      </Routes>
    </div>
  </Router>
);

export default App;
