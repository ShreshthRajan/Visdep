// frontend/src/pages/graphchat.jsx
import React, { useState, useCallback, useRef, useEffect } from 'react';
import DependencyGraph from '../components/DependencyGraph';
import Chatbot from '../components/Chatbot';
import { useNavigate } from 'react-router-dom';


const GraphChat = () => {
  const [graphWidth, setGraphWidth] = useState(70); // Adjusted to 50% for better layout
  const resizeTimeoutRef = useRef(null);
  const navigate = useNavigate();

  const handleResize = useCallback((mouseDownEvent) => {
    const startX = mouseDownEvent.clientX;
    const startWidth = graphWidth;

    const doDrag = (mouseMoveEvent) => {
      const newWidth = startWidth + (mouseMoveEvent.clientX - startX) / window.innerWidth * 100;
      setGraphWidth(Math.max(20, Math.min(newWidth, 60))); // Limit between 30% and 70%
    };

    const stopDrag = () => {
      document.removeEventListener('mousemove', doDrag);
      document.removeEventListener('mouseup', stopDrag);
    };

    document.addEventListener('mousemove', doDrag);
    document.addEventListener('mouseup', stopDrag);
  }, [graphWidth]);

  useEffect(() => {
    if (resizeTimeoutRef.current) {
      clearTimeout(resizeTimeoutRef.current);
    }
    resizeTimeoutRef.current = setTimeout(() => {
      window.dispatchEvent(new Event('resize'));
    }, 100);
  }, [graphWidth]);

  return (
    <div className="flex flex-col h-screen bg-gray-100">
      <div className="bg-blue-600 p-4 text-white">
        <h1 className="text-2xl font-bold">Visdep</h1>
      </div>
      <div className="flex flex-1 overflow-hidden">
        <div style={{ width: `${graphWidth}%` }} className="bg-white p-4 relative overflow-hidden shadow-md">
          <h2 className="text-xl font-bold mb-2 text-gray-800">Dependency Graph</h2>
          <div className="absolute inset-0 mt-12">
            <DependencyGraph />
          </div>
        </div>
        <div
          className="cursor-col-resize bg-gray-300 w-2 hover:bg-gray-400 transition duration-200"
          onMouseDown={handleResize}
        ></div>
        <div style={{ width: `${100 - graphWidth}%` }} className="bg-white p-4 overflow-hidden shadow-md">
          <h2 className="text-xl font-bold mb-2 text-gray-800">Chatbot</h2>
          <Chatbot />
        </div>
      </div>
    </div>
  );
};

export default GraphChat;
