import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import GraphChat from './pages/GraphChat';

const App = () => (
  <Router>
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/graph-chat" element={<GraphChat />} />
    </Routes>
  </Router>
);

export default App;