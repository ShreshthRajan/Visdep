import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import DependencyGraph from '../components/DependencyGraph';
import Chatbot from '../components/Chatbot';

const GraphChat = () => {
  const [graphWidth, setGraphWidth] = useState(65);
  const navigate = useNavigate();

  const handleResize = useCallback((e) => {
    const newWidth = (e.clientX / window.innerWidth) * 100;
    setGraphWidth(Math.max(30, Math.min(newWidth, 70)));
  }, []);

  useEffect(() => {
    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleResize);
    };

    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleResize);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [handleResize]);

  return (
    <div className="flex flex-col h-screen bg-gray-100 font-sans">
      <header className="bg-indigo-700 text-white p-4 flex justify-between items-center">
        <h1 className="text-2xl font-bold">Visdep</h1>
        <button 
          onClick={() => navigate('/')} 
          className="bg-white text-indigo-700 px-4 py-2 rounded-md text-sm font-medium hover:bg-indigo-100 transition-colors"
        >
          Upload New Repo
        </button>
      </header>
      <div className="flex flex-1 overflow-hidden">
        <div style={{ width: `${graphWidth}%` }} className="bg-white shadow-lg">
          <div className="h-full">
            <DependencyGraph />
          </div>
        </div>
        <div
          className="w-1 bg-gray-300 cursor-col-resize hover:bg-gray-400 transition-colors"
          onMouseDown={() => document.addEventListener('mousemove', handleResize)}
        />
        <div style={{ width: `${100 - graphWidth}%` }} className="bg-white shadow-lg flex flex-col">
          <Chatbot />
        </div>
      </div>
    </div>
  );
};

export default GraphChat;