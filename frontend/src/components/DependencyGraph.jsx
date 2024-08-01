import React, { useEffect, useRef, useState } from 'react';
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

  useEffect(() => {
    const fetchGraphData = async () => {
      try {
        const response = await axios.get('http://localhost:8000/api/dependency_graph');
        const data = response.data;
        setGraphData(data);
        renderGraph(data);
      } catch (error) {
        console.error('Error fetching graph data:', error);
      }
    };

    fetchGraphData();
  }, []);

  const renderGraph = (data) => {
    const nodes = new DataSet(data.nodes.map(node => ({
      ...node,
      shape: getNodeShape(node.type),
      color: getNodeColor(node.type),
      font: { size: 14, face: 'Arial', color: '#000000' },
      size: getNodeSize(node.type),
      title: getNodeTooltip(node),
      widthConstraint: { minimum: 100, maximum: 200 },
      heightConstraint: { minimum: 50 },
    })));
  
    const edges = new DataSet(data.edges.map(edge => ({
      from: edge.source,
      to: edge.target,
      arrows: edge.relation === 'imports' ? 'to' : '',
      color: getEdgeColor(edge.relation),
      width: 2,
      smooth: { type: 'cubicBezier', forceDirection: 'horizontal', roundness: 0.4 },
      font: { size: 10, align: 'middle', background: '#90EE90', strokeWidth: 0 },
      label: edge.label || '',
    })));

    const container = networkRef.current;
    const graphData = { nodes, edges };
    const options = {
      layout: {
        hierarchical: {
          enabled: true,
          direction: 'UD',
          sortMethod: 'directed',
          levelSeparation: 250,
          nodeSpacing: 200,
          treeSpacing: 200,
        },
      },
      physics: false,
      interaction: {
        dragNodes: true,
        dragView: true,
        zoomView: true,
        hover: true,
      },
      nodes: {
        scaling: {
          min: 20,
          max: 60,
        },
        margin: 10,
      },
      edges: {
        width: 2,
        arrows: {
          to: { enabled: true, scaleFactor: 1, type: 'arrow' }
        },
      },
    };

    const newNetwork = new Network(container, graphData, options);
    setNetwork(newNetwork);

    newNetwork.once('stabilizationIterationsDone', () => {
      newNetwork.fit({ animation: { duration: 1000, easingFunction: 'easeOutQuart' } });
    });
  };

  useEffect(() => {
    if (graphData) {
      const filteredNodes = graphData.nodes.filter(node => 
        selectedNodeTypes[node.type] &&
        (searchTerm === '' || node.label.toLowerCase().includes(searchTerm.toLowerCase()))
      );
      const filteredNodeIds = new Set(filteredNodes.map(node => node.id));
      const filteredEdges = graphData.edges.filter(edge => 
        filteredNodeIds.has(edge.source) && filteredNodeIds.has(edge.target)
      );

      renderGraph({ nodes: filteredNodes, edges: filteredEdges });
    }
  }, [selectedNodeTypes, searchTerm, graphData]);

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
      case 'import': return 'box';
      case 'package': return 'star';
      default: return 'ellipse';
    }
  };
  
  const getNodeColor = (type) => {
    if (type === 'import') {
      return { border: '#32CD32', background: '#90EE90' };
    }
    return nodeTypes[type] || nodeTypes.default;
  };

  const getNodeSize = (type) => {
    switch (type) {
      case 'directory': return 30;
      case 'file': return 25;
      case 'import': return 15;
      case 'package': return 20;
      default: return 20;
    }
  };

  const getNodeTooltip = (node) => {
    return `<div style="font-size: 14px; padding: 10px;">
      <strong>${node.label}</strong><br>
      Type: ${node.type}
    </div>`;
  };

  const getEdgeColor = (relation) => {
    switch (relation) {
      case 'contains': return '#A9A9A9';
      case 'imports': return '#4169E1';
      case 'exports': return '#32CD32';
      default: return '#000000';
    }
  };

  const getEdgeArrows = (relation) => {
    return relation === 'imports' ? 'to' : '';
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
    <div style={{ height: '100%', width: '100%', position: 'relative' }}>
      <div ref={networkRef} style={{ height: '100%', width: '100%' }} />
      <div style={{ position: 'absolute', top: 20, left: 20, zIndex: 1000 }}>
        <input
          type="text"
          placeholder="Search nodes..."
          value={searchTerm}
          onChange={handleSearch}
          style={searchInputStyle}
        />
        <button onClick={handleFitGraph} style={smallButtonStyle} title="Fit Graph">
          <i className="fas fa-expand-arrows-alt"></i>
        </button>
        <button onClick={handleZoomIn} style={smallButtonStyle} title="Zoom In">
          <i className="fas fa-search-plus"></i>
        </button>
        <button onClick={handleZoomOut} style={smallButtonStyle} title="Zoom Out">
          <i className="fas fa-search-minus"></i>
        </button>
      </div>
      <div style={legendStyle(isLegendMinimized)}>
        <div style={legendHeaderStyle}>
          <h3 style={{ margin: 0, fontSize: '16px' }}>Legend</h3>
          <button onClick={toggleLegend} style={minimizeButtonStyle}>
            {isLegendMinimized ? '+' : '-'}
          </button>
        </div>
        {!isLegendMinimized && (
          <div>
            {Object.entries(nodeTypes).map(([type, color]) => (
              <div key={type} style={legendItemStyle} onClick={() => handleNodeTypeToggle(type)}>
                <span style={{
                  ...legendColorStyle,
                  backgroundColor: color.background,
                  borderColor: color.border,
                  opacity: selectedNodeTypes[type] ? 1 : 0.5,
                }}></span>
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

const nodeTypes = {
  directory: { border: '#FF4500', background: '#FFA07A' },
  file: { border: '#4169E1', background: '#87CEFA' },
  import: { border: '#32CD32', background: '#90EE90' },
  package: { border: '#FFD700', background: '#FFFACD' },
  default: { border: '#A9A9A9', background: '#D3D3D3' },
};

const smallButtonStyle = {
  margin: '0 5px 0 0',
  padding: '5px 10px',
  backgroundColor: '#4CAF50',
  color: 'white',
  border: 'none',
  borderRadius: '4px',
  cursor: 'pointer',
  fontSize: '14px',
};

const searchInputStyle = {
  padding: '5px 10px',
  marginRight: '10px',
  borderRadius: '4px',
  border: '1px solid #ccc',
  fontSize: '14px',
};

const legendStyle = (isMinimized) => ({
  position: 'absolute',
  top: 20,
  right: 20,
  background: 'white',
  padding: '15px',
  border: '1px solid #ccc',
  borderRadius: '4px',
  zIndex: 1000,
  boxShadow: '0 2px 5px rgba(0,0,0,0.1)',
  cursor: 'pointer',
  width: isMinimized ? 'auto' : '200px',
});

const legendHeaderStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: '10px',
};

const minimizeButtonStyle = {
  background: 'none',
  border: 'none',
  fontSize: '18px',
  cursor: 'pointer',
  padding: '0 5px',
};

const legendItemStyle = {
  display: 'flex',
  alignItems: 'center',
  margin: '8px 0',
  fontSize: '14px',
};

const legendColorStyle = {
  width: '20px',
  height: '20px',
  marginRight: '10px',
  border: '2px solid',
  borderRadius: '4px',
};

export default DependencyGraph;