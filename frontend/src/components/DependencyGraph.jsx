import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Network, DataSet } from 'vis-network/standalone';
import axios from 'axios';

const DependencyGraph = () => {
  const networkRef = useRef(null);
  const [network, setNetwork] = useState(null);
  const [graphData, setGraphData] = useState(null);
  const [selectedNodeTypes, setSelectedNodeTypes] = useState({
    directory: true,
    file: true,
    import: true,
    package: true,
  });
  const [isLegendMinimized, setIsLegendMinimized] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentLevel, setCurrentLevel] = useState(1);

  const renderGraph = useCallback((data, level) => {
    const filteredNodes = data.nodes.filter(node => 
      selectedNodeTypes[node.type] && node.level <= level
    );
    const nodes = new DataSet(filteredNodes.map(node => ({
      ...node,
      shape: getNodeShape(node.type),
      color: getNodeColor(node.type),
      font: {
        size: 12,
        face: 'Arial',
        color: '#000000',
        multi: true,
        align: node.type === 'package' ? 'center' : undefined,
        valign: 'middle',
      },
      size: getNodeSize(node),
      label: getNodeLabel(node),
      title: getNodeTooltip(node),
    })));
  
    const filteredEdges = data.edges.filter(edge => {
      const fromNode = filteredNodes.find(node => node.id === edge.source);
      const toNode = filteredNodes.find(node => node.id === edge.target);
      return fromNode && toNode;
    });
    const edges = new DataSet(filteredEdges.map(edge => ({
      from: edge.source,
      to: edge.target,
      arrows: edge.relation === 'imports' ? 'to' : '',
      color: getEdgeColor(edge.relation),
      width: edge.relation === 'multiple' ? Math.log(edge.count) + 1 : 1,
      smooth: { type: 'continuous', roundness: 0.2 },
      font: { size: 12, align: 'middle', background: '#FFFFFF' },
      label: edge.relation === 'multiple' ? `${edge.count} connections` : edge.label || '',
    })));
  
    const container = networkRef.current;
    const graphData = { nodes, edges };
    const options = {
      layout: {
        improvedLayout: true,
        randomSeed: 42,
      },
      physics: {
        enabled: true,
        barnesHut: {
          gravitationalConstant: -5000,
          centralGravity: 0.3,
          springLength: 200,
          springConstant: 0.04,
          damping: 0.09,
          avoidOverlap: 1,
        },
        stabilization: {
          iterations: 1000,
          updateInterval: 25,
        },
      },
      interaction: {
        dragNodes: true,
        dragView: true,
        zoomView: true,
        hover: true,
      },
      nodes: {
        scaling: {
          min: 20,
          max: 150,
        },
        margin: 10,
        widthConstraint: {
          minimum: 50,
          maximum: 200,
        },
        heightConstraint: {
          minimum: 50,
          valign: 'center',
        },
      },
      edges: {
        smooth: {
          type: 'continuous',
          forceDirection: 'none',
          roundness: 0.2,
        },
      },
    };
  
    const newNetwork = new Network(container, graphData, options);
    setNetwork(newNetwork);
  
    newNetwork.once('stabilizationIterationsDone', () => {
      newNetwork.setOptions({ physics: false });
      newNetwork.fit({ animation: { duration: 1000, easingFunction: 'easeOutQuart' } });
    });
  
    newNetwork.on('selectNode', (params) => {
      if (params.nodes.length > 0) {
        const selectedNodeId = params.nodes[0];
        highlightConnectedNodes(selectedNodeId, nodes, edges, newNetwork);
      }
    });
  
    newNetwork.on('deselectNode', () => {
      resetNodeStyles(nodes, edges, newNetwork);
    });
  
    newNetwork.on('doubleClick', (params) => {
      if (params.nodes.length > 0) {
        const clickedNode = nodes.get(params.nodes[0]);
        if (clickedNode.level === currentLevel) {
          setCurrentLevel(prev => prev + 1);
        }
      }
    });
  }, [selectedNodeTypes, currentLevel]);  

  useEffect(() => {
    const fetchGraphData = async () => {
      try {
        const response = await axios.get('http://localhost:8000/api/dependency_graph');
        const data = response.data;
        setGraphData(data);
        renderGraph(data, currentLevel);
      } catch (error) {
        console.error('Error fetching graph data:', error);
      }
    };

    fetchGraphData();
  }, [renderGraph, currentLevel]);

  const highlightConnectedNodes = (nodeId, nodes, edges, network) => {
    const connectedNodeIds = new Set();
    edges.get().forEach(edge => {
      if (edge.from === nodeId) connectedNodeIds.add(edge.to);
      if (edge.to === nodeId) connectedNodeIds.add(edge.from);
    });

    nodes.update(nodes.get().map(node => ({
      ...node,
      color: connectedNodeIds.has(node.id) || node.id === nodeId
        ? getNodeColor(node.type)
        : { background: '#D3D3D3', border: '#A9A9A9' },
      font: { ...node.font, color: connectedNodeIds.has(node.id) || node.id === nodeId ? '#000000' : '#999999' },
    })));

    edges.update(edges.get().map(edge => ({
      ...edge,
      color: edge.from === nodeId || edge.to === nodeId ? getEdgeColor(edge.relation) : '#D3D3D3',
    })));
  };

  const resetNodeStyles = (nodes, edges, network) => {
    nodes.update(nodes.get().map(node => ({
      ...node,
      color: getNodeColor(node.type),
      font: { ...node.font, color: '#000000' },
    })));

    edges.update(edges.get().map(edge => ({
      ...edge,
      color: getEdgeColor(edge.relation),
    })));
  };

  useEffect(() => {
    if (graphData) {
      const filteredNodes = new Set();
      const queue = [];

      const addNodeAndRelated = (nodeId) => {
        if (!filteredNodes.has(nodeId)) {
          filteredNodes.add(nodeId);
          queue.push(nodeId);
        }
      };

      if (searchTerm) {
        graphData.nodes.forEach(node => {
          if (node.label.toLowerCase().includes(searchTerm.toLowerCase())) {
            addNodeAndRelated(node.id);
          }
        });

        graphData.edges.forEach(edge => {
          const sourceNode = graphData.nodes.find(node => node.id === edge.source);
          if (sourceNode && sourceNode.label.toLowerCase().includes(searchTerm.toLowerCase())) {
            addNodeAndRelated(edge.target);
          }
        });
      } else {
        graphData.nodes.forEach(node => addNodeAndRelated(node.id));
      }

      while (queue.length > 0) {
        const currentNodeId = queue.shift();
        const currentNode = graphData.nodes.find(node => node.id === currentNodeId);

        if (currentNode.type === 'file') {
          let dirPath = currentNodeId.split('/').slice(0, -1).join('/');
          while (dirPath) {
            addNodeAndRelated(dirPath);
            dirPath = dirPath.split('/').slice(0, -1).join('/');
          }
        }

        graphData.edges.forEach(edge => {
          if (edge.target === currentNodeId && edge.relation === 'imports') {
            addNodeAndRelated(edge.source);
          }
          if (edge.source === currentNodeId && edge.relation === 'exports') {
            addNodeAndRelated(edge.target);
          }
        });
      }

      const filteredNodesArray = graphData.nodes.filter(node => filteredNodes.has(node.id));
      const filteredEdges = graphData.edges.filter(edge => 
        filteredNodes.has(edge.source) && filteredNodes.has(edge.target)
      );

      renderGraph({ nodes: filteredNodesArray, edges: filteredEdges }, currentLevel);
    }
  }, [selectedNodeTypes, searchTerm, graphData, renderGraph, currentLevel]);

  const handleNodeTypeToggle = (type) => {
    setSelectedNodeTypes(prev => ({ ...prev, [type]: !prev[type] }));
  };

  const handleSearch = (event) => {
    setSearchTerm(event.target.value);
  };

  const getNodeShape = (type) => {
    switch (type) {
      case 'directory': return 'box';
      case 'file': return 'ellipse';
      case 'import': return 'diamond';
      case 'package': return 'star';
      default: return 'ellipse';
    }
  };
  
  const getNodeColor = (type) => {
    return nodeTypes[type] || nodeTypes.default;
  };

  const getNodeSize = (node) => {
    const baseSize = 30;
    const textLength = node.label.length;
    return Math.max(baseSize, Math.min(textLength * 5, 150));
  };

  const getNodeLabel = (node) => {
    return `${node.label}\n${node.type}`;
  };

  const getNodeTooltip = (node) => {
    return `<div style="font-size: 14px; padding: 10px;">
      <strong>${node.label}</strong><br>
      Type: ${node.type}<br>
      Level: ${node.level}
    </div>`;
  };

  const getEdgeColor = (relation) => {
    switch (relation) {
      case 'contains': return '#A9A9A9';
      case 'imports': return '#4169E1';
      case 'exports': return '#32CD32';
      case 'multiple': return '#FF4500';
      default: return '#000000';
    }
  };

  const handleFitGraph = () => {
    if (network) {
      network.fit({ animation: { duration: 1000, easingFunction: 'easeOutQuart' } });
    }
  };

  const handleZoomIn = () => {
    if (network) {
      const scale = network.getScale() * 1.2;
      network.moveTo({ scale: scale });
    }
  };

  const handleZoomOut = () => {
    if (network) {
      const scale = network.getScale() / 1.2;
      network.moveTo({ scale: scale });
    }
  };

  const toggleLegend = () => {
    setIsLegendMinimized(!isLegendMinimized);
  };

  return (
    <div className="h-full flex flex-col relative">
      <div className="flex justify-between items-center p-4 bg-gray-100 border-b">
        <div className="flex items-center flex-grow mr-4">
          <input
            type="text"
            placeholder="Search nodes..."
            value={searchTerm}
            onChange={handleSearch}
            className="w-full px-4 py-2 border rounded-l focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <button onClick={handleSearch} className="px-4 py-2 bg-indigo-600 text-white rounded-r hover:bg-indigo-700 transition-colors">
            Search
          </button>
        </div>
        <div className="flex">
          <button onClick={handleFitGraph} className="p-2 bg-gray-200 rounded-l hover:bg-gray-300 transition-colors" title="Fit Graph">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
            </svg>
          </button>
          <button onClick={handleZoomIn} className="p-2 bg-gray-200 hover:bg-gray-300 transition-colors" title="Zoom In">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v3m0 0v3m0-3h3m-3 0H7" />
            </svg>
          </button>
          <button onClick={handleZoomOut} className="p-2 bg-gray-200 hover:bg-gray-300 transition-colors" title="Zoom Out">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM13 10H7" />
            </svg>
          </button>
        </div>
        <div className="flex items-center ml-4">
          <button onClick={() => setCurrentLevel(prev => prev + 1)} className="p-2 bg-gray-200 hover:bg-gray-300 transition-colors" title="Increase Level">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
          </button>
          <button onClick={() => setCurrentLevel(prev => Math.max(prev - 1, 1))} className="p-2 bg-gray-200 hover:bg-gray-300 transition-colors" title="Decrease Level">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
            </svg>
          </button>
        </div>
      </div>
      <div className="flex-1 relative">
        <div ref={networkRef} className="absolute inset-0" />
        <div className={`absolute bottom-4 right-4 bg-white rounded-lg shadow-md transition-all ${isLegendMinimized ? 'w-8 h-8' : 'w-40'}`}>
          <button 
            onClick={toggleLegend} 
            className="absolute top-1 right-1 text-gray-500 hover:text-gray-700"
            title={isLegendMinimized ? "Expand Legend" : "Minimize Legend"}
          >
            {isLegendMinimized ? (
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16m-7 6h7" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            )}
          </button>
          {!isLegendMinimized && (
            <div className="p-2 pt-6">
              {Object.entries(nodeTypes).map(([type, color]) => (
                <div key={type} className="flex items-center mb-1 cursor-pointer" onClick={() => handleNodeTypeToggle(type)}>
                  <span
                    className={`w-3 h-3 rounded-full mr-2 ${selectedNodeTypes[type] ? 'opacity-100' : 'opacity-50'}`}
                    style={{ backgroundColor: color.background, borderColor: color.border, borderWidth: 1 }}
                  />
                  <span className={`text-xs ${selectedNodeTypes[type] ? 'text-gray-800' : 'text-gray-500'}`}>
                    {type.charAt(0).toUpperCase() + type.slice(1)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const nodeTypes = {
  directory: { border: '#34495e', background: '#ecf0f1' },
  file: { border: '#2980b9', background: '#e0f7fa' },
  import: { border: '#27ae60', background: '#e9f7ef' },
  package: { border: '#f39c12', background: '#fef5e7' },
  default: { border: '#95a5a6', background: '#f4f6f6' },
};

export default DependencyGraph;