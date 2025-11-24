// frontend/src/components/dependencygraph.jsx
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Network, DataSet } from 'vis-network/standalone';
import API from '../api';
import NodeChatPanel from './NodeChatPanel';

const DependencyGraph = ({ highlightedNodes = [], onNodeQuery }) => {
  const networkRef = useRef(null);
  const [network, setNetwork] = useState(null);
  const [graphData, setGraphData] = useState(null);
  const [viewMode, setViewMode] = useState('full');  // 'full' or 'focused'
  const [repoSize, setRepoSize] = useState('medium');  // 'small', 'medium', 'large'
  const [contextMenu, setContextMenu] = useState(null);  // { x, y, node }
  const [activeChatNode, setActiveChatNode] = useState(null);  // Node with inline chat open
  const [selectedNodeTypes, setSelectedNodeTypes] = useState({
    directory: true,
    file: true,
    import: false,
    package: false,
    class_definition: true,  // Will be set adaptively
    function: true,  // Will be set adaptively
    method: false,
    module_variable: false,
  });
  const [nodeFading, setNodeFading] = useState({
    class_definition: true,  // Show faded by default for medium repos
    function: true,  // Show faded by default for medium repos
  });
  const [isLegendMinimized, setIsLegendMinimized] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentLevel, setCurrentLevel] = useState(4);
  const [loadingState, setLoadingState] = useState({ isLoading: false, message: '', progress: 0 });
  const [megaRepoWarning, setMegaRepoWarning] = useState(null);


  const renderGraph = useCallback((data, level) => {
    // Set initial rendering state
    setLoadingState({ isLoading: true, message: 'Preparing graph...', progress: 40 });

    // Adaptive stabilization iterations based on graph complexity
    // Research: Force-Atlas2 converges exponentially (80% settled in first 30%)
    // vis-network docs recommend 200-1000 iterations for most graphs
    // Optimization: Reduce iterations without sacrificing visual quality (40-50% faster rendering)
    const getStabilizationIterations = (nodeCount) => {
      if (nodeCount < 200) {
        // Small repos: Fast stabilization (1-2 seconds)
        return 300;
      } else if (nodeCount < 1000) {
        // Medium repos: Balanced (3-4 seconds)
        return 800;
      } else {
        // Large repos: More iterations for complex graphs (5-6 seconds vs 8-10s before)
        return 1500;
      }
    };

    const stabilizationIterations = getStabilizationIterations(data.nodes.length);
    console.log(`🚀 PERFORMANCE: Using ${stabilizationIterations} iterations for ${data.nodes.length} nodes (adaptive optimization)`);

    // Dual-mode filtering: Full structure view vs Highlight-focused view
    const filteredNodes = data.nodes.filter(node => {
      // FOCUSED MODE: Show only highlighted nodes + their parents
      if (viewMode === 'focused' && highlightedNodes.length > 0) {
        // Always include highlighted nodes
        if (highlightedNodes.includes(node.id)) {
          return true;
        }

        // Include parent containers (files, directories) for context
        // Check if any highlighted node is a child of this node
        const isParentOfHighlight = highlightedNodes.some(hId => {
          // Check if highlighted node's path includes this node's ID
          return hId.startsWith(node.id);
        });

        if (isParentOfHighlight && (node.type === 'file' || node.type === 'directory')) {
          return true;
        }

        return false;  // Hide everything else in focused mode
      }

      // FULL MODE: Show structure (directories, files, classes)
      // Always include highlighted nodes regardless of level/type
      if (highlightedNodes.includes(node.id)) {
        return true;
      }

      // Otherwise apply checkbox filtering (ignore level if user explicitly enabled type)
      return selectedNodeTypes[node.type];
    });
    const nodes = new DataSet(filteredNodes.map(node => {
      // Check if this node should be highlighted
      const isHighlighted = highlightedNodes.includes(node.id);

      // Determine opacity based on node type and fading settings
      const isFaded = nodeFading[node.type] && !isHighlighted;
      const opacity = isFaded ? 0.35 : 1.0;  // 35% opacity for faded, full for others

      // Get base color
      const baseColor = isHighlighted
        ? { background: '#F59E0B', border: '#D97706' }  // Amber for highlighted (always full opacity)
        : getNodeColor(node.type);

      // Apply opacity to color
      const colorWithOpacity = {
        background: baseColor.background,
        border: baseColor.border,
        highlight: {
          background: baseColor.background,
          border: baseColor.border,
        },
        hover: {
          background: baseColor.background,
          border: baseColor.border,
        },
      };

      return {
        ...node,
        shape: getNodeShape(node.type),
        color: colorWithOpacity,
        opacity: opacity,  // Set node opacity
        font: {
          size: isFaded ? 11 : 13,  // Slightly larger
          face: "'Inter', system-ui, -apple-system, sans-serif",
          color: isFaded ? '#999999' : '#E0E0E0',  // Light text for dark nodes
          multi: true,
          align: (node.type === 'package' || node.type === 'import') ? 'center' : undefined,
          valign: (node.type === 'package' || node.type === 'import') ? 'middle' : undefined,
        },
        size: getNodeSize(node),
        label: getNodeLabel(node),
      };
    }));
  
    const filteredEdges = data.edges.filter(edge => {
      const fromNode = filteredNodes.find(node => node.id === edge.source);
      const toNode = filteredNodes.find(node => node.id === edge.target);
      return fromNode && toNode;
    });
    const edges = new DataSet(filteredEdges.map(edge => {
      const edgeColor = getEdgeColor(edge.relation);
      return {
        from: edge.source,
        to: edge.target,
        arrows: edge.relation === 'imports' ? 'to' : '',
        color: {
          color: edgeColor.color,
          opacity: edgeColor.opacity,
          highlight: edgeColor.color,
          hover: edgeColor.color
        },
        width: edge.relation === 'multiple' ? Math.log(edge.count) + 1 : 1.5,
        smooth: { type: 'continuous', roundness: 0.2 },
        font: { size: 11, align: 'middle', background: 'transparent', color: 'var(--text-secondary)' },
        label: edge.relation === 'multiple' ? `${edge.count} connections` : edge.label || '',
      };
    }));
  
    const container = networkRef.current;
    const graphData = { nodes, edges };
    const options = {
      layout: {
        improvedLayout: true,
        randomSeed: 42,  // Consistent layout across reloads
      },
      physics: {
        enabled: true,
        solver: 'forceAtlas2Based',  // Community detection algorithm (enterprise-grade)
        forceAtlas2Based: {
          gravitationalConstant: -150,  // Strong repulsion (spread nodes apart for readability)
          centralGravity: 0.005,  // Very weak center (allows wide spreading)
          springLength: 150,  // Longer springs (more space between nodes)
          springConstant: 0.04,  // Weaker connections (less clustering force)
          damping: 0.6,  // High damping (settle faster, less bouncing)
          avoidOverlap: 1.5,  // Strong overlap prevention (critical for 400+ nodes)
        },
        stabilization: {
          enabled: true,
          iterations: stabilizationIterations,  // Adaptive: 300/800/1500 based on repo size
          updateInterval: 25,
          fit: true,
        },
        maxVelocity: 30,  // Limit maximum movement speed
        minVelocity: 0.5,  // Stop when movement is minimal
      },
      interaction: {
        hover: true,
        hoverConnectedEdges: true,
        selectConnectedEdges: false,
        dragNodes: true,
        dragView: true,
        zoomView: true,
      },
      nodes: {
        scaling: {
          min: 25,  // Larger minimum (more readable)
          max: 200,  // Larger maximum
        },
        margin: 15,  // More space around nodes
        widthConstraint: {
          minimum: 60,  // Larger minimum width
          maximum: 250,  // Wider max for long method names
        },
        heightConstraint: {
          minimum: 60,  // Taller nodes
          valign: 'center',
        },
        font: {
          size: 13,
          face: "'Inter', system-ui, -apple-system, sans-serif",
          color: '#E0E0E0',
          bold: {
            size: 14,
            face: "'Inter', system-ui, -apple-system, sans-serif",
            color: '#E0E0E0'
          },
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

    // Show progress during stabilization (live updates)
    newNetwork.on('stabilizationProgress', (params) => {
      const progress = Math.round((params.iterations / params.total) * 100);
      setLoadingState({
        isLoading: true,
        message: `Organizing clusters...`,
        progress: 50 + (progress / 2)  // 50-100% range
      });
      if (progress % 20 === 0) {  // Log every 20%
        console.log(`📊 GRAPH: Organizing clusters... ${progress}%`);
      }
    });

    // Force-Atlas2 clustering: Let physics organize, then lock positions
    newNetwork.once('stabilizationIterationsDone', () => {
      console.log('✅ GRAPH: Clustering complete, locking positions');
      setLoadingState({ isLoading: true, message: 'Finalizing layout...', progress: 95 });
      newNetwork.setOptions({ physics: { enabled: false } });  // Lock positions (no more movement)
      newNetwork.fit({ animation: { duration: 1000, easingFunction: 'easeInOutQuad' } });

      // Mark as complete after animation
      setTimeout(() => {
        setLoadingState({ isLoading: false, message: '', progress: 100 });
      }, 1000);
    });

    newNetwork.on('hoverNode', (params) => {
      const nodeId = params.node;
      const node = nodes.get(nodeId);
      const connectedNodes = newNetwork.getConnectedNodes(nodeId);
      const imports = connectedNodes.filter(id => {
        const edge = edges.get(newNetwork.getConnectedEdges(nodeId, id)[0]);
        return edge && edge.arrows === 'to' && edge.to === nodeId;
      });
      const fileStructure = connectedNodes.filter(id => {
        const connectedNode = nodes.get(id);
        return connectedNode.type === 'directory';
      });

      const tooltipContent = `
        <div style="font-size: 14px; padding: 10px;">
          <strong>File Name: ${node.label}</strong><br>
          Type: ${node.type}<br>
          Level: ${node.level}<br>
          Imports: ${imports.map(id => nodes.get(id).label).join(', ')}<br>
          File structure: /${fileStructure.map(id => nodes.get(id).label).join('/')}
        </div>
      `;

      newNetwork.body.nodes[nodeId].options.title = tooltipContent;
    });

    newNetwork.on('click', (params) => {
      // Close context menu on any click
      setContextMenu(null);

      if (params.nodes.length > 0) {
        const clickedNodeId = params.nodes[0];
        highlightConnectedNodes(clickedNodeId, newNetwork, nodes, edges);
      } else {
        resetHighlight(newNetwork, nodes, edges);
      }
    });

    // Right-click context menu
    newNetwork.on('oncontext', (params) => {
      params.event.preventDefault();

      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        const node = nodes.get(nodeId);

        setContextMenu({
          x: params.pointer.DOM.x,
          y: params.pointer.DOM.y,
          node: node
        });
      }
    });

  }, [selectedNodeTypes, currentLevel, highlightedNodes, viewMode, nodeFading]);

  // Auto-switch to focused mode when highlights appear
  useEffect(() => {
    if (highlightedNodes.length > 0) {
      console.log('🎯 AUTO-SWITCH: Switching to focused view (highlighting detected)');
      setViewMode('focused');
    }
  }, [highlightedNodes]);

  // Re-render graph when highlighted nodes change
  useEffect(() => {
    console.log('🎨 GRAPH DEBUG: highlightedNodes changed:', highlightedNodes);

    if (!graphData) {
      console.log('ℹ️ GRAPH: No graph data yet');
      return;
    }

    if (highlightedNodes.length > 0) {
      console.log('✅ GRAPH: Processing highlights...');
      console.log('   Graph has', graphData.nodes.length, 'nodes');
      console.log('   View mode:', viewMode);
      console.log('   Attempting to highlight:', highlightedNodes);

      // Check if any highlighted nodes exist in graph
      const matchingNodes = graphData.nodes.filter(node => highlightedNodes.includes(node.id));
      console.log('   Matching nodes found:', matchingNodes.length);

      if (matchingNodes.length === 0) {
        console.warn('⚠️ GRAPH: No matching nodes found! Highlighted IDs don\'t match graph node IDs');
        console.warn('   Sample highlighted ID:', highlightedNodes[0]);
        console.warn('   Sample graph node ID:', graphData.nodes[0]?.id);
        console.warn('   Total graph nodes:', graphData.nodes.length);
      } else {
        console.log('✅ GRAPH: Found matching nodes:', matchingNodes.map(n => n.id));
        console.log('💡 TIP: Gold nodes are now visible in the graph - use Fit Graph button or zoom to see them');

        // Note: Auto-zoom removed for reliability
        // Gold highlighting makes nodes easy to find visually
        // User can click "Fit Graph" button to see full graph
        // Or manually zoom/pan to highlighted nodes
        // This is more reliable than programmatic focus() which has timing issues
      }

      // Re-render graph to apply highlighting
      // Note: Don't call renderGraph here - it's already in the renderGraph useCallback dependencies
      // The graph will re-render automatically when highlightedNodes changes via the renderGraph callback
    } else {
      console.log('ℹ️ GRAPH: No nodes to highlight (empty array)');
    }
  }, [highlightedNodes, graphData, network, viewMode]);  // Added viewMode to fix focused view rendering

  // Render graph when data or filters change (but not when searching)
  useEffect(() => {
    if (graphData && !searchTerm) {
      console.log('🎨 Re-rendering graph with current filters');
      renderGraph(graphData, currentLevel);
    }
  }, [graphData, selectedNodeTypes, currentLevel, nodeFading, renderGraph, searchTerm, viewMode]);

  // Fetch graph data once on mount
  useEffect(() => {
    const fetchGraphData = async () => {
      try {
        setLoadingState({ isLoading: true, message: 'Loading graph data...', progress: 10 });
        const response = await API.get('/api/dependency_graph');
        const data = response.data;
        setLoadingState({ isLoading: true, message: 'Analyzing graph structure...', progress: 30 });

        // Check for mega-repo warning from backend
        if (data.mega_repo_warning) {
          setMegaRepoWarning(data.mega_repo_warning);
          console.warn('⚠️ MEGA-REPO:', data.mega_repo_warning);
        }

        setGraphData(data);

        // Adaptive defaults based on repository size
        const totalNodes = data.nodes.length;
        console.log(`📊 Repository size: ${totalNodes} nodes`);

        if (totalNodes < 200) {
          // Small repo: Show everything
          setRepoSize('small');
          setSelectedNodeTypes(prev => ({
            ...prev,
            class_definition: true,
            function: true,
          }));
          setNodeFading({ class_definition: false, function: false });
          setCurrentLevel(4);
          console.log('✅ Small repo detected: Showing all details');
        } else if (totalNodes < 1000) {
          // Medium repo: Show files + faded classes/functions
          setRepoSize('medium');
          setSelectedNodeTypes(prev => ({
            ...prev,
            class_definition: true,
            function: true,
          }));
          setNodeFading({ class_definition: true, function: true });
          setCurrentLevel(4);
          console.log('✅ Medium repo detected: Showing files + faded classes/functions');
        } else {
          // Large repo: Files only, hide classes/functions
          setRepoSize('large');
          setSelectedNodeTypes(prev => ({
            ...prev,
            class_definition: false,
            function: false,
          }));
          setNodeFading({ class_definition: false, function: false });
          setCurrentLevel(3);
          console.log('✅ Large repo detected: Showing files only');
        }

        // Don't call renderGraph here - it will be called by the renderGraph useEffect
        // when graphData state updates
      } catch (error) {
        console.error('Error fetching graph data:', error);
      }
    };

    fetchGraphData();
  }, []);  // Only run once on mount - removed circular dependencies

  const highlightConnectedNodes = (nodeId, network, nodes, edges) => {
    const connectedNodeIds = network.getConnectedNodes(nodeId);
    connectedNodeIds.push(nodeId);
    network.selectNodes(connectedNodeIds);

    // Highlight edges connected to this node in green
    const connectedEdgeIds = network.getConnectedEdges(nodeId);
    const edgeUpdates = connectedEdgeIds.map(edgeId => ({
      id: edgeId,
      color: {
        color: '#10B981',
        opacity: 1.0,
        highlight: '#10B981',
        hover: '#10B981'
      },
      width: 2
    }));
    edges.update(edgeUpdates);
  };

  const resetHighlight = (network, nodes, edges) => {
    network.unselectAll();

    // Reset all edges to original colors
    const allEdges = edges.get();
    const edgeResets = allEdges.map(edge => {
      const edgeColor = getEdgeColor(edge.relation || 'default');
      return {
        id: edge.id,
        color: {
          color: edgeColor.color,
          opacity: edgeColor.opacity,
          highlight: edgeColor.color,
          hover: edgeColor.color
        },
        width: edge.relation === 'multiple' ? Math.log(edge.count || 1) + 1 : 1.5
      };
    });
    edges.update(edgeResets);
  };

  // Handle search separately from regular rendering
  useEffect(() => {
    if (graphData && searchTerm) {
      const filteredNodes = new Set();
      const queue = [];

      const addNodeAndRelated = (nodeId) => {
        if (!filteredNodes.has(nodeId)) {
          filteredNodes.add(nodeId);
          queue.push(nodeId);
        }
      };

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

      while (queue.length > 0) {
        const currentNodeId = queue.shift();
        const currentNode = graphData.nodes.find(node => node.id === currentNodeId);

        if (currentNode && currentNode.type === 'file') {
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
  }, [searchTerm, graphData, renderGraph, currentLevel]);

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
      case 'import': return 'circle';
      case 'package': return 'circle';
      default: return 'ellipse';
    }
  };
  
  const getNodeColor = (type) => {
    return nodeTypes[type] || nodeTypes.default;
  };

  const getNodeSize = (node) => {
    if (node.type === 'import' || node.type === 'package') {
    return 15; // Smaller size for import and package nodes
  }
    const baseSize = 30;
    const textLength = node.label.length;
    return Math.max(baseSize, Math.min(textLength * 5, 150));
  };

  const getNodeLabel = (node) => {
    if (node.type === 'package') {
      return node.label; // Only show the package name for star-shaped nodes
    }
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
      case 'contains': return { color: '#4B5563', opacity: 0.5 };
      case 'imports': return { color: '#10B981', opacity: 0.7 };
      case 'exports': return { color: '#3B82F6', opacity: 0.7 };
      case 'multiple': return { color: '#F59E0B', opacity: 0.8 };
      default: return { color: '#4B5563', opacity: 0.4 };
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

  const handleAskAboutNode = (node) => {
    // Close context menu
    setContextMenu(null);

    // Open inline chat panel for this node
    setActiveChatNode(node);
  };

  return (
    <div className="h-full flex flex-col relative">
      {/* Mega-Repo Warning */}
      {megaRepoWarning && (
        <div className="bg-yellow-50 border-b-2 border-yellow-400 p-2 text-center">
          <span className="text-sm font-semibold text-yellow-900">
            ⚠️ Large Repository ({megaRepoWarning.chunk_count.toLocaleString()} chunks) - {megaRepoWarning.message}
          </span>
          <span className="text-xs text-yellow-700 ml-2">{megaRepoWarning.example}</span>
          <button onClick={() => setMegaRepoWarning(null)} className="ml-3 text-yellow-700 hover:text-yellow-900 font-bold">✕</button>
        </div>
      )}
      <div className="flex justify-between items-center p-4" style={{
        backgroundColor: 'var(--near-black)',
        borderBottom: '1px solid var(--border-subtle)'
      }}>
        <div className="flex items-center flex-grow mr-4">
          {/* View Mode Toggle */}
          {highlightedNodes.length > 0 && (
            <button
              onClick={() => setViewMode(viewMode === 'full' ? 'focused' : 'full')}
              className="mr-4 px-4 py-2 rounded font-medium transition-all"
              style={{
                backgroundColor: viewMode === 'focused' ? 'var(--highlight)' : 'var(--elevated)',
                color: '#ffffff',
                border: 'none',
                cursor: 'pointer'
              }}
              title={viewMode === 'focused' ? 'Show full repository structure' : 'Focus on highlighted results'}
              onMouseEnter={(e) => e.target.style.opacity = '0.9'}
              onMouseLeave={(e) => e.target.style.opacity = '1'}
            >
              {viewMode === 'focused' ? '🎯 Focused View' : '📊 Full Structure'}
            </button>
          )}

          <input
            type="text"
            placeholder="Search nodes..."
            value={searchTerm}
            onChange={handleSearch}
            className="w-full px-4 py-2 rounded-l focus:outline-none transition-all"
            style={{
              backgroundColor: 'var(--input-bg)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-default)',
              fontFamily: "'Inter', sans-serif"
            }}
            onFocus={(e) => e.target.style.borderColor = 'var(--accent)'}
            onBlur={(e) => e.target.style.borderColor = 'var(--border-default)'}
          />
          <button
            onClick={handleSearch}
            className="px-4 py-2 rounded-r transition-all font-medium"
            style={{
              backgroundColor: '#84a07c',
              color: '#ffffff',
              border: 'none',
              cursor: 'pointer'
            }}
            onMouseEnter={(e) => e.target.style.opacity = '0.9'}
            onMouseLeave={(e) => e.target.style.opacity = '1'}
          >
            Search
          </button>
        </div>
        <div className="flex">
          <button
            onClick={handleFitGraph}
            className="p-2 rounded-l transition-all"
            style={{ backgroundColor: 'var(--elevated)', color: 'var(--text-primary)' }}
            title="Fit Graph"
            onMouseEnter={(e) => e.target.style.backgroundColor = 'var(--card-bg)'}
            onMouseLeave={(e) => e.target.style.backgroundColor = 'var(--elevated)'}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
            </svg>
          </button>
          <button
            onClick={handleZoomIn}
            className="p-2 transition-all"
            style={{ backgroundColor: 'var(--elevated)', color: 'var(--text-primary)' }}
            title="Zoom In"
            onMouseEnter={(e) => e.target.style.backgroundColor = 'var(--card-bg)'}
            onMouseLeave={(e) => e.target.style.backgroundColor = 'var(--elevated)'}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v3m0 0v3m0-3h3m-3 0H7" />
            </svg>
          </button>
          <button
            onClick={handleZoomOut}
            className="p-2 transition-all"
            style={{ backgroundColor: 'var(--elevated)', color: 'var(--text-primary)' }}
            title="Zoom Out"
            onMouseEnter={(e) => e.target.style.backgroundColor = 'var(--card-bg)'}
            onMouseLeave={(e) => e.target.style.backgroundColor = 'var(--elevated)'}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM13 10H7" />
            </svg>
          </button>
        </div>
        <div className="flex items-center ml-4">
          <button
            onClick={() => setCurrentLevel(prev => prev + 1)}
            className="p-2 transition-all"
            style={{ backgroundColor: 'var(--elevated)', color: 'var(--text-primary)' }}
            title="Increase Level"
            onMouseEnter={(e) => e.target.style.backgroundColor = 'var(--card-bg)'}
            onMouseLeave={(e) => e.target.style.backgroundColor = 'var(--elevated)'}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
          </button>
          <button
            onClick={() => setCurrentLevel(prev => Math.max(prev - 1, 1))}
            className="p-2 transition-all"
            style={{ backgroundColor: 'var(--elevated)', color: 'var(--text-primary)' }}
            title="Decrease Level"
            onMouseEnter={(e) => e.target.style.backgroundColor = 'var(--card-bg)'}
            onMouseLeave={(e) => e.target.style.backgroundColor = 'var(--elevated)'}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
            </svg>
          </button>
        </div>
      </div>
      <div className="flex-1 relative">
        {/* Loading Overlay */}
        {loadingState.isLoading && (
          <div className="absolute inset-0 z-50 flex flex-col items-center justify-center" style={{
            backgroundColor: 'rgba(0, 0, 0, 0.95)',
            backdropFilter: 'blur(8px)'
          }}>
            <div className="p-6 rounded-lg shadow-lg max-w-md w-full" style={{
              backgroundColor: 'var(--card-bg)',
              border: '1px solid var(--border-default)'
            }}>
              <div className="flex items-center justify-center mb-4">
                <div className="animate-spin rounded-full h-12 w-12" style={{
                  borderWidth: '3px',
                  borderStyle: 'solid',
                  borderColor: 'var(--border-default)',
                  borderTopColor: 'var(--accent)'
                }}></div>
              </div>
              <p className="text-center font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
                {loadingState.message}
              </p>
              <div className="w-full rounded-full h-2.5" style={{ backgroundColor: 'var(--border-default)' }}>
                <div
                  className="h-2.5 rounded-full transition-all duration-300"
                  style={{
                    width: `${loadingState.progress}%`,
                    backgroundColor: 'var(--accent)'
                  }}
                ></div>
              </div>
              <p className="text-center text-sm mt-2" style={{ color: 'var(--text-secondary)' }}>
                {loadingState.progress}%
              </p>
            </div>
          </div>
        )}
        <div ref={networkRef} className="absolute inset-0" />
        <div
          className={`absolute bottom-4 right-4 rounded-lg shadow-md transition-all ${isLegendMinimized ? 'w-10 h-10' : 'w-64'}`}
          style={{
            backgroundColor: 'rgba(26, 26, 26, 0.95)',
            backdropFilter: 'blur(12px)',
            border: '1px solid var(--border-default)',
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.8)'
          }}
        >
          <button
            onClick={toggleLegend}
            className="absolute top-2 right-2 transition-colors"
            style={{ color: 'var(--text-secondary)' }}
            title={isLegendMinimized ? "Expand Legend" : "Minimize Legend"}
            onMouseEnter={(e) => e.target.style.color = 'var(--text-primary)'}
            onMouseLeave={(e) => e.target.style.color = 'var(--text-secondary)'}
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
            <div className="p-3 pt-8">
              <div className="text-xs font-semibold mb-3" style={{ color: 'var(--text-secondary)' }}>
                Repo: {repoSize} ({graphData?.nodes.length} nodes)
              </div>
              {Object.entries(nodeTypes).map(([type, color]) => (
                <div key={type} className="mb-2">
                  <div className="flex items-center cursor-pointer" onClick={() => handleNodeTypeToggle(type)}>
                    <input
                      type="checkbox"
                      checked={selectedNodeTypes[type]}
                      onChange={() => {}}
                      className="mr-2 cursor-pointer"
                      style={{ accentColor: 'var(--accent)' }}
                    />
                    <span
                      className="w-3 h-3 rounded mr-1"
                      style={{
                        backgroundColor: color.background,
                        border: `2px solid ${color.border}`,
                        opacity: selectedNodeTypes[type] ? (nodeFading[type] ? 0.35 : 1.0) : 0.2
                      }}
                    />
                    <span className="text-xs" style={{
                      color: selectedNodeTypes[type] ? 'var(--text-primary)' : 'var(--text-tertiary)'
                    }}>
                      {type.charAt(0).toUpperCase() + type.slice(1).replace('_', ' ')}
                      {selectedNodeTypes[type] && nodeFading[type] && (
                        <span style={{ color: 'var(--text-tertiary)' }} className="ml-1">(faded)</span>
                      )}
                    </span>
                  </div>
                  {/* Fading toggle for classes and functions */}
                  {selectedNodeTypes[type] && (type === 'class_definition' || type === 'function') && (
                    <div className="ml-6 mt-1">
                      <label className="flex items-center cursor-pointer text-xs" style={{ color: 'var(--text-secondary)' }}>
                        <input
                          type="checkbox"
                          checked={!nodeFading[type]}
                          onChange={() => setNodeFading(prev => ({ ...prev, [type]: !prev[type] }))}
                          className="mr-1 cursor-pointer"
                          style={{ accentColor: 'var(--accent)' }}
                          onClick={(e) => e.stopPropagation()}
                        />
                        Full opacity
                      </label>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Context Menu */}
        {contextMenu && (
          <div
            className="absolute rounded-lg shadow-lg py-1 z-50"
            style={{
              left: `${contextMenu.x}px`,
              top: `${contextMenu.y}px`,
              backgroundColor: 'var(--card-bg)',
              border: '1px solid var(--border-default)',
              minWidth: '220px',
              boxShadow: '0 12px 48px rgba(0, 0, 0, 0.9)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => handleAskAboutNode(contextMenu.node)}
              className="w-full text-left px-4 py-2.5 transition-colors flex items-center"
              style={{
                color: 'var(--text-primary)',
                fontFamily: "'Inter', sans-serif",
                fontSize: '0.875rem',
                border: 'none',
                background: 'none',
                cursor: 'pointer'
              }}
              onMouseEnter={(e) => e.target.style.backgroundColor = 'var(--elevated)'}
              onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
            >
              <span className="mr-2">💬</span>
              Ask about {contextMenu.node.label.split('\n')[0]}
            </button>
            <div style={{ height: '1px', backgroundColor: 'var(--border-subtle)', margin: '0.25rem 0' }} />
            <button
              onClick={() => {
                setContextMenu(null);
                if (network) {
                  network.selectNodes([contextMenu.node.id]);
                  highlightConnectedNodes(contextMenu.node.id, network);
                }
              }}
              className="w-full text-left px-4 py-2.5 transition-colors flex items-center"
              style={{
                color: 'var(--text-primary)',
                fontFamily: "'Inter', sans-serif",
                fontSize: '0.875rem',
                border: 'none',
                background: 'none',
                cursor: 'pointer'
              }}
              onMouseEnter={(e) => e.target.style.backgroundColor = 'var(--elevated)'}
              onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
            >
              <span className="mr-2">🔍</span>
              Show dependencies
            </button>
            <button
              onClick={() => {
                setContextMenu(null);
                console.log('Full node data:', contextMenu.node);
              }}
              className="w-full text-left px-4 py-2.5 transition-colors flex items-center"
              style={{
                color: 'var(--text-primary)',
                fontFamily: "'Inter', sans-serif",
                fontSize: '0.875rem',
                border: 'none',
                background: 'none',
                cursor: 'pointer'
              }}
              onMouseEnter={(e) => e.target.style.backgroundColor = 'var(--elevated)'}
              onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
            >
              <span className="mr-2">📄</span>
              View full info
            </button>
          </div>
        )}

        {/* Inline Node Chat Panel */}
        {activeChatNode && (
          <NodeChatPanel
            node={activeChatNode}
            onClose={() => setActiveChatNode(null)}
          />
        )}
      </div>
    </div>
  );
}

const nodeTypes = {
  directory: { border: '#4B5563', background: '#374151' },
  file: { border: '#4B5563', background: '#1F2937' },
  import: { border: '#10B981', background: '#065F46' },
  package: { border: '#10B981', background: '#064E3B' },
  class_definition: { border: '#8B5CF6', background: '#6B21A8' },
  function: { border: '#3B82F6', background: '#1E40AF' },
  method: { border: '#A855F7', background: '#7E22CE' },
  module_variable: { border: '#10B981', background: '#065F46' },
  default: { border: '#4B5563', background: '#374151' },
};

export default DependencyGraph;