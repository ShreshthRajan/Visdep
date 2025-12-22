// frontend/src/components/dependencygraph.jsx
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Network, DataSet } from 'vis-network/standalone';
import { Rnd } from 'react-rnd';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import API from '../api';

const DependencyGraph = ({ highlightedNodes = [], onNodeSelect, onNodeDragStart, onNodeDragEnd }) => {
  const networkRef = useRef(null);
  const [network, setNetwork] = useState(null);
  const [graphData, setGraphData] = useState(null);
  const [viewMode, setViewMode] = useState('full');  // 'full' or 'focused'
  const [repoSize, setRepoSize] = useState('medium');  // 'small', 'medium', 'large'
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
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentLevel, setCurrentLevel] = useState(4);
  const [loadingState, setLoadingState] = useState({ isLoading: false, message: '', progress: 0 });
  const [megaRepoWarning, setMegaRepoWarning] = useState(null);

  // Query node system state
  const [queryNodes, setQueryNodes] = useState({});  // { nodeId: { parentId, conversation, badgePosition } }
  const [activeQueryInput, setActiveQueryInput] = useState(null);  // { nodeId, position }
  const [selectedNodeButtons, setSelectedNodeButtons] = useState(null);  // { nodeId, position }
  const [explanationTooltip, setExplanationTooltip] = useState(null);  // { nodeId, text, position }
  const [responsePanels, setResponsePanels] = useState({});  // { nodeId: { position, size, isVisible } }


  const renderGraph = useCallback((data, level) => {
    // Set initial rendering state
    setLoadingState({ isLoading: true, message: 'Preparing graph...', progress: 40 });

    // CRITICAL: Preserve existing query nodes before rebuild
    let existingQueryNodes = [];
    let existingQueryEdges = [];

    if (network && network.body && network.body.data) {
      const currentNodes = network.body.data.nodes;
      const currentEdges = network.body.data.edges;

      if (currentNodes && currentEdges) {
        // Extract query nodes
        existingQueryNodes = currentNodes.get({
          filter: (node) => node.type === 'query_node'
        });

        // Extract query edges
        existingQueryEdges = currentEdges.get({
          filter: (edge) => edge.id && edge.id.startsWith('edge_query_')
        });

        console.log(`💾 Preserving ${existingQueryNodes.length} query nodes and ${existingQueryEdges.length} query edges`);
      }
    }

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

      // Neural Blue Theme: Cyan for highlighted citations
      const baseColor = isHighlighted
        ? { background: '#22d3ee', border: '#ffffff' }  // Electric cyan with white border
        : getNodeColor(node.type);

      // Apply opacity to color + selection styling
      const colorWithOpacity = {
        background: baseColor.background,
        border: baseColor.border,
        highlight: {
          background: '#22d3ee',  // Electric cyan when clicked
          border: '#ffffff',  // White border for sharp contrast
        },
        hover: {
          background: baseColor.background,
          border: '#22d3ee',  // Cyan border on hover
        },
      };

      return {
        ...node,
        shape: getNodeShape(node.type),
        shapeProperties: {
          borderRadius: 6,  // Enterprise-grade rounded corners (6px)
        },
        color: colorWithOpacity,
        opacity: opacity,  // Set node opacity
        borderWidth: 2,
        borderWidthSelected: 3,
        font: {
          size: isFaded ? 10 : 11,  // Dense
          face: 'JetBrains Mono',
          color: isHighlighted ? '#ffffff' : (isFaded ? '#71717a' : '#f4f4f5'),  // Pure white for highlighted
          multi: true,
          align: (node.type === 'package' || node.type === 'import') ? 'center' : undefined,
          valign: (node.type === 'package' || node.type === 'import') ? 'middle' : undefined,
          strokeWidth: isHighlighted ? 3 : 0,  // Dark halo for readability
          strokeColor: isHighlighted ? '#000000' : undefined,
        },
        shadow: isHighlighted ? {
          enabled: true,
          color: 'rgba(34, 211, 238, 0.6)',  // Electric cyan glow
          size: 30,  // Larger bloom for "Sun" effect
          x: 0,
          y: 0
        } : undefined,
        size: getNodeSize(node),
        label: getNodeLabel(node),
      };
    }));

    // RE-ADD preserved query nodes after creating base nodes
    if (existingQueryNodes.length > 0) {
      nodes.add(existingQueryNodes);
      console.log(`✅ Re-added ${existingQueryNodes.length} query nodes`);
    }

    const filteredEdges = data.edges.filter(edge => {
      const fromNode = filteredNodes.find(node => node.id === edge.source);
      const toNode = filteredNodes.find(node => node.id === edge.target);
      return fromNode && toNode;
    });
    const edges = new DataSet(filteredEdges.map(edge => {
      const baseColor = getEdgeColor(edge.relation);
      return {
        from: edge.source,
        to: edge.target,
        arrows: edge.relation === 'imports' ? { to: { enabled: true, scaleFactor: 0.8 } } : '',
        color: {
          color: baseColor,
          highlight: '#22d3ee',  // Electric cyan when edge is selected (trace flow)
          hover: '#22d3ee',  // Cyan on hover
          opacity: 0.7,  // Slightly transparent by default
        },
        width: edge.relation === 'multiple' ? Math.log(edge.count) + 1 : 1.5,
        selectionWidth: 4,  // Thicker when selected - show AST flow
        smooth: {
          type: 'continuous',
          roundness: 0.2,
          forceDirection: 'none',
        },
        font: {
          size: 11,
          align: 'middle',
          background: 'rgba(255, 255, 255, 0.8)',
          strokeWidth: 0,
        },
        label: edge.relation === 'multiple' ? `${edge.count}×` : '',
        chosen: {
          edge: true,  // Enable custom styling when selected
          label: false,
        },
      };
    }));

    // RE-ADD preserved query edges after creating base edges
    if (existingQueryEdges.length > 0) {
      edges.add(existingQueryEdges);
      console.log(`✅ Re-added ${existingQueryEdges.length} query edges`);
    }

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
        selectConnectedEdges: true,  // Auto-select connected edges (enterprise feature)
        dragNodes: true,
        dragView: true,
        zoomView: true,
        multiselect: false,  // Single selection only (cleaner UX)
        navigationButtons: false,
        keyboard: {
          enabled: true,
          bindToWindow: false,
        },
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
          size: 13,  // Larger base font
          face: 'system-ui, -apple-system, "Segoe UI", sans-serif',
          color: '#1a1a1a',
          bold: {
            size: 14,
            face: 'system-ui, -apple-system, "Segoe UI", sans-serif',
          },
        },
      },
      edges: {
        smooth: {
          type: 'continuous',
          forceDirection: 'none',
          roundness: 0.2,
        },
        color: {
          opacity: 0.7,  // Default transparency
        },
        width: 1.5,  // Slightly thicker default
        selectionWidth: 3,  // Even thicker when selected
        hoverWidth: 2,  // Increase on hover
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

    // REMOVED: Hover tooltips disabled - they show ugly HTML and aren't useful
    // Click interaction will open clean chat panel instead

    // Drag-and-drop to chat for multi-node context using global mouseup
    // Standard canvas drag pattern: dragStart on canvas, mouseup on window
    newNetwork.on('dragStart', (params) => {
      if (params.nodes.length > 0 && onNodeDragStart) {
        const draggedNodeId = params.nodes[0];
        const draggedNode = nodes.get(draggedNodeId);
        onNodeDragStart(draggedNode);
        console.log('🎯 Drag started:', draggedNode.label);

        // Add GLOBAL mouseup listener (fires even outside canvas)
        const handleGlobalMouseUp = (e) => {
          if (onNodeDragEnd) {
            const mousePos = {
              x: e.clientX,
              y: e.clientY
            };
            onNodeDragEnd(mousePos);
            console.log('🎯 Global mouseup at:', mousePos);
          }

          // Cleanup: Remove global listener after single use
          window.removeEventListener('mouseup', handleGlobalMouseUp);
        };

        window.addEventListener('mouseup', handleGlobalMouseUp);
      }
    });

    // Enterprise-grade click handler with connected highlighting
    newNetwork.on('click', (params) => {
      if (params.nodes.length > 0) {
        const clickedNodeId = params.nodes[0];
        const clickedNode = nodes.get(clickedNodeId);

        // Get connected nodes and edges for full context visualization
        const connectedNodeIds = newNetwork.getConnectedNodes(clickedNodeId);
        const connectedEdgeIds = newNetwork.getConnectedEdges(clickedNodeId);

        // Highlight: selected node + connected nodes + connecting edges
        // This uses vis-network's native selection with highlightEdges = true
        newNetwork.selectNodes([clickedNodeId], true);

        // Enterprise feature: Dim non-connected nodes for focus
        // Performance optimization: batch update with single pass
        const allNodeIds = nodes.getIds();
        const highlightedNodeIds = new Set([clickedNodeId, ...connectedNodeIds]);

        const nodesToUpdate = allNodeIds.map(nodeId => ({
          id: nodeId,
          opacity: highlightedNodeIds.has(nodeId) ? 1.0 : 0.1,  // 90% dimming - spatial focus
        }));

        nodes.update(nodesToUpdate);  // Batch update for performance

        // Log for debugging
        console.log('🖱️ Node clicked:', clickedNode.label, clickedNode.type);
        console.log('📊 Connected:', connectedNodeIds.length, 'nodes,', connectedEdgeIds.length, 'edges');

        // Send to HUD Inspector
        if (onNodeSelect) {
          onNodeSelect(clickedNode);
        }

        // Show action buttons for all code nodes
        const canvasPos = newNetwork.getPositions([clickedNodeId])[clickedNodeId];
        const screenPos = newNetwork.canvasToDOM(canvasPos);

        setSelectedNodeButtons({
          nodeId: clickedNodeId,
          node: clickedNode,
          position: {
            x: screenPos.x,
            y: screenPos.y + 50
          }
        });
      } else {
        // Clicked on empty canvas - restore all nodes and deselect
        const allNodeIds = nodes.getIds();
        allNodeIds.forEach(nodeId => {
          const nodeData = nodes.get(nodeId);
          // Restore original opacity based on fading state
          const originalOpacity = (nodeFading[nodeData.type] && !highlightedNodes.includes(nodeId)) ? 0.35 : 1.0;
          nodes.update({
            id: nodeId,
            opacity: originalOpacity,
          });
        });
        newNetwork.unselectAll();
        setSelectedNodeButtons(null);
        setActiveQueryInput(null);

        // Clear HUD selection
        if (onNodeSelect) {
          onNodeSelect(null);
        }
      }
    });

  }, [selectedNodeTypes, currentLevel, highlightedNodes, viewMode, nodeFading, onNodeSelect]);

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

  // Node selection is now handled inline in click handler (see renderGraph)

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
    // Enterprise-grade: All nodes use 'box' shape with rounded corners
    // Circles only for small connector nodes (imports/packages)
    switch (type) {
      case 'import': return 'dot';  // Small circular dot for imports
      case 'package': return 'dot';  // Small circular dot for packages
      default: return 'box';  // All code entities use rounded boxes
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

  // Tooltip function removed - was causing ugly HTML display on hover
  // Node interaction now uses clean click-to-query pattern

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

  const toggleFilter = () => {
    setIsFilterOpen(!isFilterOpen);
  };

  // Query node system handlers
  const createQueryNode = useCallback((parentNode) => {
    if (!network) return;

    const parentPos = network.getPositions([parentNode.id])[parentNode.id];
    const screenPos = network.canvasToDOM(parentPos);
    const queryNodeId = `query_${parentNode.id}_${Date.now()}`;

    // Store parent position for later
    setQueryNodes(prev => ({
      ...prev,
      [queryNodeId]: {
        parentId: parentNode.id,
        parentPosition: parentPos,
        conversation: []
      }
    }));

    // Show search bar input immediately (attached under node)
    setActiveQueryInput({
      nodeId: queryNodeId,
      parentNode: parentNode,
      position: {
        x: screenPos.x,
        y: screenPos.y + 55
      }
    });

    setSelectedNodeButtons(null);
  }, [network]);

  // No query node clicks needed - panels are HTML, not graph nodes

  const handleQuerySubmit = useCallback(async (queryNodeId, question, parentNode) => {
    if (!question.trim()) return;

    const parentPos = network.getPositions([parentNode.id])[parentNode.id];
    const screenPos = network.canvasToDOM(parentPos);

    // Show thinking panel immediately (NO graph node)
    setResponsePanels(prev => ({
      ...prev,
      [queryNodeId]: {
        position: { x: screenPos.x + 60, y: screenPos.y - 50 },
        size: { width: 400, height: 500 },
        isVisible: true,
        isThinking: true,
        parentNodeId: parentNode.id,
        parentPosition: parentPos
      }
    }));

    setActiveQueryInput(null);

    try {
      // OPTION C: Send node context for focused retrieval
      const response = await API.post('/api/query', {
        query: question,
        node_context: {
          chunk_id: parentNode.id,
          name: parentNode.label?.split('\n')[0] || parentNode.id,
          type: parentNode.type
        }
      });
      const answer = response.data.response || response.data;

      // Update panel with response
      setResponsePanels(prev => ({
        ...prev,
        [queryNodeId]: {
          ...prev[queryNodeId],
          isThinking: false
        }
      }));

      // Store conversation
      setQueryNodes(prev => ({
        ...prev,
        [queryNodeId]: {
          ...prev[queryNodeId],
          conversation: [...(prev[queryNodeId]?.conversation || []), { q: question, a: answer }]
        }
      }));
    } catch (error) {
      console.error('Query error:', error);
      setResponsePanels(prev => ({
        ...prev,
        [queryNodeId]: {
          ...prev[queryNodeId],
          isThinking: false,
          error: true
        }
      }));

      setQueryNodes(prev => ({
        ...prev,
        [queryNodeId]: {
          ...prev[queryNodeId],
          conversation: [{ q: question, a: 'Error: Could not process query' }]
        }
      }));
    }
  }, [network, queryNodes]);

  // Old functions removed - using HTML panels now

  const handleQuickExplain = useCallback(async (node) => {
    if (!network) return;

    const canvasPos = network.getPositions([node.id])[node.id];
    const screenPos = network.canvasToDOM(canvasPos);

    // Show loading tooltip immediately
    setExplanationTooltip({
      nodeId: node.id,
      position: { x: screenPos.x, y: screenPos.y + 60 },
      text: 'Analyzing...',
      loading: true
    });

    setSelectedNodeButtons(null);

    try {
      // Fast explain endpoint with full node context
      const response = await API.post('/api/explain_node', {
        chunk_id: node.id,
        name: node.label?.split('\n')[0] || node.id,  // Clean name (first line only)
        type: node.type,
        file_path: node.id  // chunk_id contains file path
      });

      setExplanationTooltip({
        nodeId: node.id,
        position: { x: screenPos.x, y: screenPos.y + 60 },
        text: response.data.explanation,
        loading: false
      });

      // Auto-dismiss after 10 seconds
      setTimeout(() => {
        setExplanationTooltip(null);
      }, 10000);
    } catch (error) {
      console.error('Explain error:', error);
      setExplanationTooltip({
        nodeId: node.id,
        position: { x: screenPos.x, y: screenPos.y + 60 },
        text: 'Error: Could not generate explanation',
        loading: false
      });
    }
  }, [network]);

  // Panels are react-rnd managed, no position tracking needed

  // Close filter dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (isFilterOpen && !e.target.closest('.filter-dropdown-container')) {
        setIsFilterOpen(false);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [isFilterOpen]);

  return (
    <div className="h-full flex flex-col relative">
      {/* Mega-Repo Warning */}
      {/* Modern 2025 Toolbar */}
      {megaRepoWarning && (
        <div style={{ backgroundColor: 'var(--elevated)', borderBottom: '1px solid var(--border-default)' }} className="p-2 text-center">
          <span className="text-sm font-medium" style={{ color: 'var(--text-primary)', fontFamily: "'Inter', sans-serif" }}>
            Large Repository ({megaRepoWarning.chunk_count.toLocaleString()} chunks) - {megaRepoWarning.message}
          </span>
          <button onClick={() => setMegaRepoWarning(null)} className="ml-3 hover:opacity-75 font-medium" style={{ color: 'var(--text-secondary)' }}>×</button>
        </div>
      )}
      {/* Floating Island Control - Top Center */}
      <div className="absolute top-6 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1.5 px-3 py-2 rounded-full" style={{
        backgroundColor: 'rgba(9, 9, 11, 0.4)',
        backdropFilter: 'blur(16px)',
        border: '1px solid rgba(255, 255, 255, 0.1)'
      }}>
        {/* Quick Filters - Segmented Control */}
        <button
          onClick={() => handleNodeTypeToggle('directory')}
          className="px-2 py-1 text-[10px] font-medium transition-all rounded-md"
          style={{
            backgroundColor: selectedNodeTypes['directory'] ? 'rgba(113, 113, 122, 0.2)' : 'transparent',
            color: selectedNodeTypes['directory'] ? '#f4f4f5' : '#52525b',
            fontFamily: "'JetBrains Mono', monospace",
            textTransform: 'uppercase',
            letterSpacing: '0.5px'
          }}
          title="Toggle directories"
        >
          DIR
        </button>
        <button
          onClick={() => handleNodeTypeToggle('file')}
          className="px-2 py-1 text-[10px] font-medium transition-all rounded-md"
          style={{
            backgroundColor: selectedNodeTypes['file'] ? 'rgba(59, 130, 246, 0.2)' : 'transparent',
            color: selectedNodeTypes['file'] ? '#3b82f6' : '#52525b',
            fontFamily: "'JetBrains Mono', monospace",
            textTransform: 'uppercase',
            letterSpacing: '0.5px'
          }}
          title="Toggle files"
        >
          FILE
        </button>
        <button
          onClick={() => handleNodeTypeToggle('class_definition')}
          className="px-2 py-1 text-[10px] font-medium transition-all rounded-md"
          style={{
            backgroundColor: selectedNodeTypes['class_definition'] ? 'rgba(139, 92, 246, 0.2)' : 'transparent',
            color: selectedNodeTypes['class_definition'] ? '#8b5cf6' : '#52525b',
            fontFamily: "'JetBrains Mono', monospace",
            textTransform: 'uppercase',
            letterSpacing: '0.5px'
          }}
          title="Toggle classes"
        >
          CLASS
        </button>
        <button
          onClick={() => handleNodeTypeToggle('method')}
          className="px-2 py-1 text-[10px] font-medium transition-all rounded-md"
          style={{
            backgroundColor: selectedNodeTypes['method'] ? 'rgba(167, 139, 250, 0.2)' : 'transparent',
            color: selectedNodeTypes['method'] ? '#a78bfa' : '#52525b',
            fontFamily: "'JetBrains Mono', monospace",
            textTransform: 'uppercase',
            letterSpacing: '0.5px'
          }}
          title="Toggle methods"
        >
          METH
        </button>

        {/* Full/Focus appears when highlighted */}
        {highlightedNodes.length > 0 && (
          <>
            <div style={{ width: '1px', height: '14px', backgroundColor: 'rgba(255, 255, 255, 0.08)', margin: '0 4px' }} />
            <button
              onClick={() => setViewMode(viewMode === 'full' ? 'focused' : 'full')}
              className="px-2 py-1 text-[10px] font-medium transition-all rounded-md"
              style={{
                backgroundColor: viewMode === 'focused' ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
                color: viewMode === 'focused' ? '#3b82f6' : '#71717a',
                border: viewMode === 'focused' ? '1px solid rgba(59, 130, 246, 0.3)' : '1px solid transparent',
                fontFamily: "'JetBrains Mono', monospace",
                textTransform: 'uppercase'
              }}
            >
              {viewMode === 'focused' ? '✕ FOCUS' : 'FOCUS'}
            </button>
          </>
        )}
      </div>

      <div className="flex-1 relative">
        {/* Loading Overlay - Hidden (we use Loading.jsx page instead) */}
        {false && loadingState.isLoading && (
          <div className="absolute inset-0 z-50 flex flex-col items-center justify-center" style={{ backgroundColor: 'rgba(5, 5, 5, 0.95)', backdropFilter: 'blur(4px)' }}>
            <div className="p-6 rounded-lg shadow-lg max-w-md w-full" style={{ backgroundColor: '#18181b', border: '1px solid rgba(59, 130, 246, 0.2)' }}>
              <div className="flex items-center justify-center mb-4">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2" style={{ borderColor: 'var(--accent)' }}></div>
              </div>
              <p className="text-center font-medium mb-2" style={{ color: 'var(--text-primary)', fontFamily: "'Inter', sans-serif" }}>{loadingState.message}</p>
              <div className="w-full rounded-full h-2.5" style={{ backgroundColor: 'var(--elevated)' }}>
                <div
                  className="h-2.5 rounded-full transition-all duration-300"
                  style={{ width: `${loadingState.progress}%`, backgroundColor: 'var(--accent)' }}
                ></div>
              </div>
              <p className="text-center text-sm mt-2" style={{ color: 'var(--text-secondary)', fontFamily: "'Inter', sans-serif" }}>{loadingState.progress}%</p>
            </div>
          </div>
        )}
        <div ref={networkRef} className="absolute inset-0" />
        {/* All floating elements removed - using HUD */}
      </div>
    </div>
  );
}

const nodeTypes = {
  directory: { border: '#52525b', background: '#18181b' },  // Muted zinc gray
  file: { border: '#3b82f6', background: '#18181b' },  // Blue for files
  import: { border: '#52525b', background: '#18181b' },  // Muted
  package: { border: '#52525b', background: '#18181b' },  // Muted
  class_definition: { border: '#7c3aed', background: '#18181b' },  // Darker purple for classes
  function: { border: '#3b82f6', background: '#18181b' },  // Blue for functions
  method: { border: '#8b5cf6', background: '#18181b' },  // Muted purple for methods (was too bright)
  module_variable: { border: '#52525b', background: '#18181b' },  // Muted
  default: { border: '#52525b', background: '#18181b' },  // Muted zinc gray
};

export default DependencyGraph;
