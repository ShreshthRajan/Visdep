// frontend/src/pages/GraphChat.jsx
import React, { useState, useCallback, useRef, useEffect } from 'react';
import DependencyGraph from '../components/DependencyGraph';
import Chatbot from '../components/Chatbot';

const GraphChat = () => {
  const [graphHeight, setGraphHeight] = useState(70); // Initial graph height (%)
  const resizeTimeoutRef = useRef(null);

  const handleResize = useCallback((mouseDownEvent) => {
    const startY = mouseDownEvent.clientY;
    const startHeight = graphHeight;

    const doDrag = (mouseMoveEvent) => {
      const newHeight = startHeight + (mouseMoveEvent.clientY - startY) / window.innerHeight * 100;
      setGraphHeight(Math.max(20, Math.min(newHeight, 80))); // Limit between 20% and 80%
    };

    const stopDrag = () => {
      document.removeEventListener('mousemove', doDrag);
      document.removeEventListener('mouseup', stopDrag);
    };

    document.addEventListener('mousemove', doDrag);
    document.addEventListener('mouseup', stopDrag);
  }, [graphHeight]);

  useEffect(() => {
    if (resizeTimeoutRef.current) {
      clearTimeout(resizeTimeoutRef.current);
    }
    resizeTimeoutRef.current = setTimeout(() => {
      window.dispatchEvent(new Event('resize'));
    }, 100);
  }, [graphHeight]);

  return (
    <div className="flex flex-col h-screen">
      <div style={{ height: `${graphHeight}%` }} className="bg-gray-100 p-4 relative">
        <h2 className="text-2xl font-bold mb-4">Dependency Graph</h2>
        <div className="absolute inset-0 mt-12">
          <DependencyGraph />
        </div>
      </div>
      <div
        className="cursor-row-resize bg-gray-300 h-2"
        onMouseDown={handleResize}
      ></div>
      <div style={{ height: `${100 - graphHeight}%` }} className="bg-white p-4 overflow-auto">
        <h2 className="text-2xl font-bold mb-4">Chatbot</h2>
        <Chatbot />
      </div>
    </div>
  );
};

export default GraphChat;