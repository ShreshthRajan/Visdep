// frontend/src/components/Navbar.jsx
import React from 'react';
import { Link } from 'react-router-dom';

const Navbar = () => (
  <nav>
    <ul>
      <li><Link to="/">Home</Link></li>
      <li><Link to="/upload">Upload</Link></li>
      <li><Link to="/chat">Chat</Link></li>
      <li><Link to="/graph">Graph</Link></li>
    </ul>
  </nav>
);

export default Navbar;
