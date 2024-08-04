// frontend/src/components/navbar.jsx
import React from 'react';
import { Link } from 'react-router-dom';

const Navbar = () => (
  <nav className="bg-blue-600 p-4 text-white">
    <ul className="flex space-x-4">
      <li><Link to="/">Home</Link></li>
      <li><Link to="/upload">Upload</Link></li>
      <li><Link to="/graph-chat">Graph & Chat</Link></li>
    </ul>
  </nav>
);

export default Navbar;
