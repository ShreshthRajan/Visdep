// frontend/src/components/dependencygraph.jsx
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Network, DataSet } from 'vis-network/standalone';
import API from '../api';
import LZString from 'lz-string';
import graphStorage from '../utils/graphStorage';

const DependencyGraph = ({ highlightedNodes = [], onNodeSelect, onNodeDragStart, currentRepoId = null }) => {
  const networkRef = useRef(null);
  const [network, setNetwork] = useState(null);
  const [graphData, setGraphData] = useState(null);
  const [viewMode, setViewMode] = useState('full');  // 'full' or 'focused'
  // eslint-disable-next-line no-unused-vars
  const [repoSize, setRepoSize] = useState('medium');  // 'small', 'medium', 'large' - used for adaptive rendering
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
  const [searchQuery, setSearchQuery] = useState('');  // New search bar query
  const [searchResults, setSearchResults] = useState([]);  // Search results
  const [selectedResultIndex, setSelectedResultIndex] = useState(-1);  // Keyboard navigation
  const [isSearchFocused, setIsSearchFocused] = useState(false);
  const searchInputRef = useRef(null);
  const [loadingState, setLoadingState] = useState({ isLoading: false, message: '', progress: 0 });
  // eslint-disable-next-line no-unused-vars
  const [megaRepoWarning, setMegaRepoWarning] = useState(null);  // Used for mega-repo warnings

  // Query node system state (setters are used, values reserved for future UI)
  // eslint-disable-next-line no-unused-vars
  const [queryNodes, setQueryNodes] = useState({});  // { nodeId: { parentId, conversation, badgePosition } }
  // eslint-disable-next-line no-unused-vars
  const [activeQueryInput, setActiveQueryInput] = useState(null);  // { nodeId, position }
  // eslint-disable-next-line no-unused-vars
  const [selectedNodeButtons, setSelectedNodeButtons] = useState(null);  // { nodeId, position }
  // eslint-disable-next-line no-unused-vars
  const [explanationTooltip, setExplanationTooltip] = useState(null);  // { nodeId, text, position }
  // eslint-disable-next-line no-unused-vars
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

    // =========================================================================
    // LAYOUT: ForceAtlas2-based positioning (WebGL-accelerated)
    // =========================================================================
    // Positions are computed on the Loading page using ForceAtlas2 and saved.
    // This ensures beautiful radial clustering layouts for ALL repos.
    //
    // Modes:
    // - HYBRID: Pre-computed positions exist → instant render (most common)
    // - FULL: ForceAtlas2 fallback for small repos if somehow no positions
    // - BARNES_HUT: Fast fallback for medium repos if somehow no positions
    // =========================================================================

    const PHYSICS_MODE = {
      FULL: 'full',           // ForceAtlas2 (beautiful, best quality)
      BARNES_HUT: 'barnesHut', // Barnes-Hut O(n log n) (fast fallback)
      HYBRID: 'hybrid'        // Pre-computed positions (instant)
    };

    // Check if nodes have pre-computed positions (from Loading page ForceAtlas2)
    const hasPrecomputedPositions = data.nodes.some(n => n.x !== undefined && n.y !== undefined);

    // Determine physics mode based on positions and node count
    const getPhysicsMode = (nodeCount, hasPositions) => {
      // If positions exist, use HYBRID mode (instant render)
      if (hasPositions) return PHYSICS_MODE.HYBRID;
      // Fallback: compute layout here (shouldn't happen normally)
      // ForceAtlas2 for small, BarnesHut for larger (performance)
      if (nodeCount < 3000) return PHYSICS_MODE.FULL;
      return PHYSICS_MODE.BARNES_HUT;
    };

    const getStabilizationIterations = (nodeCount, mode) => {
      if (mode === PHYSICS_MODE.HYBRID) {
        // Pre-computed positions: No stabilization needed
        return 0;
      }
      // Fallback iterations (shouldn't run normally - Loading page computes positions)
      if (nodeCount < 200) return 300;
      if (nodeCount < 500) return 500;
      if (nodeCount < 1000) return 800;
      if (nodeCount < 3000) return 1000;
      return 1200;
    };

    const effectiveMode = getPhysicsMode(data.nodes.length, hasPrecomputedPositions);
    const stabilizationIterations = getStabilizationIterations(data.nodes.length, effectiveMode);

    console.log(`🚀 GRAPH: ${data.nodes.length} nodes, mode=${effectiveMode}, precomputed=${hasPrecomputedPositions}`);

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

      // Base node properties
      const nodeProps = {
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
      
      // HYBRID MODE: Use pre-computed x,y positions for instant render
      if (effectiveMode === PHYSICS_MODE.HYBRID && node.x !== undefined && node.y !== undefined) {
        nodeProps.x = node.x;
        nodeProps.y = node.y;
        nodeProps.physics = false;  // Don't apply physics to positioned nodes initially
      }
      
      return nodeProps;
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
    
    // =========================================================================
    // PHYSICS OPTIONS: Adaptive based on repo size
    // =========================================================================

    // Adaptive ForceAtlas2 parameters - tighter clustering for larger repos
    const getAdaptiveForceAtlas2Params = (nodeCount) => {
      if (nodeCount < 1000) {
        // Small repos: spread out, beautiful radial layout
        return {
          gravitationalConstant: -150,
          centralGravity: 0.005,
          springLength: 150,
          springConstant: 0.04,
          damping: 0.6,
          avoidOverlap: 1.5,
        };
      } else if (nodeCount < 5000) {
        // Medium repos: slightly tighter
        return {
          gravitationalConstant: -120,
          centralGravity: 0.012,
          springLength: 120,
          springConstant: 0.05,
          damping: 0.5,
          avoidOverlap: 1.2,
        };
      } else if (nodeCount < 15000) {
        // Large repos (like Django): tight clusters
        return {
          gravitationalConstant: -80,
          centralGravity: 0.025,
          springLength: 90,
          springConstant: 0.06,
          damping: 0.4,
          avoidOverlap: 1.0,
        };
      } else {
        // Mega repos: very tight, dense core
        return {
          gravitationalConstant: -50,
          centralGravity: 0.04,
          springLength: 70,
          springConstant: 0.08,
          damping: 0.35,
          avoidOverlap: 0.8,
        };
      }
    };

    const getPhysicsOptions = (mode, iterations, nodeCount) => {
      if (mode === PHYSICS_MODE.HYBRID) {
        // HYBRID MODE: Pre-computed positions, no initial physics
        // Local physics enabled on drag (see dragStart handler below)
        return {
          enabled: false,  // Start with physics OFF (instant render)
          solver: 'barnesHut',  // When enabled, use fast O(n log n) algorithm
          barnesHut: {
            gravitationalConstant: -2000,
            centralGravity: 0.3,
            springLength: 95,
            springConstant: 0.04,
            damping: 0.09
          },
          stabilization: false  // Don't re-stabilize
        };
      }

      if (mode === PHYSICS_MODE.BARNES_HUT) {
        // BARNES-HUT MODE: Fast O(n log n) for 1K-10K nodes
        // Use adaptive params based on node count
        const adaptiveGravity = nodeCount > 10000 ? 0.15 : 0.1;
        const adaptiveSpring = nodeCount > 10000 ? 100 : 120;
        return {
          enabled: true,
          solver: 'barnesHut',  // O(n log n) vs O(n²) for forceAtlas2
          barnesHut: {
            gravitationalConstant: -3000,
            centralGravity: adaptiveGravity,
            springLength: adaptiveSpring,
            springConstant: 0.04,
            damping: 0.5,
            avoidOverlap: 0.5
          },
          stabilization: {
            enabled: true,
            iterations: iterations,
            updateInterval: 25,
            fit: true
          },
          maxVelocity: 50,
          minVelocity: 0.5
        };
      }

      // FULL MODE: Beautiful ForceAtlas2 with adaptive params
      const forceAtlas2Params = getAdaptiveForceAtlas2Params(nodeCount);
      return {
        enabled: true,
        solver: 'forceAtlas2Based',  // Community detection algorithm (enterprise-grade)
        forceAtlas2Based: forceAtlas2Params,
        stabilization: {
          enabled: true,
          iterations: iterations,
          updateInterval: 25,
          fit: true,
        },
        maxVelocity: 30,
        minVelocity: 0.5
      };
    };
    
    const physicsOptions = getPhysicsOptions(effectiveMode, stabilizationIterations, data.nodes.length);
    
    const options = {
      layout: {
        improvedLayout: effectiveMode !== PHYSICS_MODE.HYBRID,  // Skip for pre-computed
        randomSeed: 42,  // Consistent layout across reloads
      },
      physics: physicsOptions,
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

    // HYBRID MODE: Skip stabilization (instant render with pre-computed positions)
    if (effectiveMode === PHYSICS_MODE.HYBRID) {
      console.log('✅ GRAPH: HYBRID mode - using pre-computed positions (instant render)');
      setLoadingState({ isLoading: true, message: 'Rendering graph...', progress: 80 });
      
      // Fit view after short delay to ensure all nodes are positioned
      setTimeout(() => {
        newNetwork.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
        setLoadingState({ isLoading: false, message: '', progress: 100 });
        console.log('✅ GRAPH: HYBRID mode render complete');
      }, 200);
    } else {
      // Show progress during stabilization (live updates)
      newNetwork.on('stabilizationProgress', (params) => {
        const progress = Math.round((params.iterations / params.total) * 100);
        setLoadingState({
          isLoading: true,
          message: `Organizing clusters (${effectiveMode})...`,
          progress: 50 + (progress / 2)  // 50-100% range
        });
        if (progress % 20 === 0) {  // Log every 20%
          console.log(`📊 GRAPH: Organizing clusters... ${progress}% (${effectiveMode})`);
        }
      });

      // Force-Atlas2/Barnes-Hut clustering: Let physics organize, then lock positions
      newNetwork.once('stabilizationIterationsDone', () => {
        console.log(`✅ GRAPH: Clustering complete (${effectiveMode}), locking positions`);
        setLoadingState({ isLoading: true, message: 'Finalizing layout...', progress: 95 });
        newNetwork.setOptions({ physics: { enabled: false } });  // Lock positions (no more movement)
        newNetwork.fit({ animation: { duration: 1000, easingFunction: 'easeInOutQuad' } });

        // MEGA-REPO: Save positions after stabilization for instant future loads
        // Only save for large repos (>3000 nodes) that don't already have pre-computed positions
        if (data.nodes.length > 3000 && !hasPrecomputedPositions && currentRepoId) {
          console.log(`💾 MEGA-REPO: Saving ${data.nodes.length} node positions for instant future loads...`);
          
          // Get all positions from vis-network
          const allPositions = newNetwork.getPositions();
          
          // Convert to storage format
          const positionsToSave = {};
          for (const [nodeId, pos] of Object.entries(allPositions)) {
            positionsToSave[nodeId] = { x: pos.x, y: pos.y };
          }
          
          // Save to backend asynchronously (don't block UI)
          API.post('/api/save_graph_positions', {
            repo_id: currentRepoId,
            positions: positionsToSave
          }).then(() => {
            console.log(`✅ MEGA-REPO: Saved ${Object.keys(positionsToSave).length} positions to backend`);
          }).catch(err => {
            console.warn(`⚠️ Failed to save positions: ${err.message}`);
          });
        }

        // Mark as complete after animation
        setTimeout(() => {
          setLoadingState({ isLoading: false, message: '', progress: 100 });
        }, 1000);
      });
    }

    // REMOVED: Hover tooltips disabled - they show ugly HTML and aren't useful
    // Click interaction will open clean chat panel instead

    // Drag-and-drop to chat using ghost element (bypasses canvas constraints)
    // HYBRID MODE: Enable local physics on drag for interactive feel
    // MEGA-REPO OPTIMIZATION: Skip physics updates for >10K nodes (O(n) freezes UI)
    const MEGA_REPO_DRAG_THRESHOLD = 10000;
    const isMegaRepoDrag = data.nodes.length > MEGA_REPO_DRAG_THRESHOLD;

    newNetwork.on('dragStart', (params) => {
      if (params.nodes.length > 0) {
        const draggedNodeId = params.nodes[0];
        const draggedNode = nodes.get(draggedNodeId);

        // HYBRID MODE: Enable local physics for dragged node + neighbors
        // MEGA-REPO: Skip physics (O(n) node updates freeze 60K+ node graphs)
        if (effectiveMode === PHYSICS_MODE.HYBRID && !isMegaRepoDrag) {
          const connectedNodes = newNetwork.getConnectedNodes(draggedNodeId);

          // Get 2-hop neighbors for smooth local physics
          const affectedNodes = new Set([draggedNodeId, ...connectedNodes]);
          connectedNodes.forEach(n => {
            newNetwork.getConnectedNodes(n).forEach(nn => affectedNodes.add(nn));
          });

          // Fix all OTHER nodes (they don't move)
          const allNodeIds = nodes.getIds();
          const updates = allNodeIds.map(nodeId => ({
            id: nodeId,
            fixed: affectedNodes.has(nodeId) ? false : { x: true, y: true }
          }));
          nodes.update(updates);

          // Enable physics for local simulation
          newNetwork.setOptions({ physics: { enabled: true } });
          console.log(`🔧 HYBRID: Enabled local physics for ${affectedNodes.size} nodes`);
        }

        // Create ghost DOM element for drag-to-chat (if handler provided)
        if (onNodeDragStart) {
          const ghost = document.createElement('div');
          const nodeName = draggedNode.label?.split('\n')[0] || draggedNode.id;
          ghost.textContent = nodeName;

          // Style ghost to match neural blue theme
          ghost.style.position = 'fixed';
          ghost.style.pointerEvents = 'none';  // Don't block mouse
          ghost.style.zIndex = '10000';
          ghost.style.padding = '6px 12px';
          ghost.style.backgroundColor = '#22d3ee';
          ghost.style.color = '#050505';
          ghost.style.borderRadius = '4px';
          ghost.style.fontSize = '11px';
          ghost.style.fontFamily = 'JetBrains Mono, monospace';
          ghost.style.fontWeight = '600';
          ghost.style.boxShadow = '0 4px 16px rgba(34, 211, 238, 0.4)';
          ghost.style.opacity = '0.95';
          ghost.style.letterSpacing = '-0.01em';

          document.body.appendChild(ghost);

          // Pass node + ghost to parent
          onNodeDragStart({ node: draggedNode, ghostElement: ghost });
          console.log('🎯 Drag started:', nodeName);
        }
      }
    });

    // HYBRID MODE: Disable physics after drag ends, lock new positions
    // MEGA-REPO: Skip (physics wasn't enabled in dragStart)
    newNetwork.on('dragEnd', (params) => {
      if (effectiveMode === PHYSICS_MODE.HYBRID && !isMegaRepoDrag && params.nodes.length > 0) {
        // Let physics settle briefly, then disable
        setTimeout(() => {
          newNetwork.setOptions({ physics: { enabled: false } });

          // Unfix all nodes for next drag
          const allNodeIds = nodes.getIds();
          const updates = allNodeIds.map(nodeId => ({
            id: nodeId,
            fixed: false
          }));
          nodes.update(updates);

          console.log('🔧 HYBRID: Physics disabled, positions locked');
        }, 500);  // 500ms for physics to settle
      }
    });

    // Enterprise-grade click handler with connected highlighting
    // MEGA-REPO OPTIMIZATION: Skip opacity dimming for >10K nodes (causes freeze)
    const MEGA_REPO_CLICK_THRESHOLD = 10000;
    const isMegaRepo = data.nodes.length > MEGA_REPO_CLICK_THRESHOLD;

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
        // MEGA-REPO: Skip opacity dimming (O(n) update freezes for 60K nodes)
        if (!isMegaRepo) {
          const allNodeIds = nodes.getIds();
          const highlightedNodeIds = new Set([clickedNodeId, ...connectedNodeIds]);

          const nodesToUpdate = allNodeIds.map(nodeId => ({
            id: nodeId,
            opacity: highlightedNodeIds.has(nodeId) ? 1.0 : 0.1,  // 90% dimming - spatial focus
          }));

          nodes.update(nodesToUpdate);  // Batch update for performance
        }

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
        // MEGA-REPO: Skip opacity restoration (wasn't dimmed in the first place)
        if (!isMegaRepo) {
          // BATCH UPDATE: Single call instead of O(n) individual updates
          const allNodeIds = nodes.getIds();
          const nodesToUpdate = allNodeIds.map(nodeId => {
            const nodeData = nodes.get(nodeId);
            const originalOpacity = (nodeFading[nodeData.type] && !highlightedNodes.includes(nodeId)) ? 0.35 : 1.0;
            return { id: nodeId, opacity: originalOpacity };
          });
          nodes.update(nodesToUpdate);
        }

        newNetwork.unselectAll();
        setSelectedNodeButtons(null);
        setActiveQueryInput(null);

        // Clear HUD selection
        if (onNodeSelect) {
          onNodeSelect(null);
        }
      }
    });

    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // Option B: Update canvas highlighting directly (performant, no full re-render)
  useEffect(() => {
    console.log('🔵 HIGHLIGHT UPDATE TRIGGERED:', {
      hasNetwork: !!network,
      hasGraphData: !!graphData,
      highlightCount: highlightedNodes.length
    });

    if (!network || !graphData) {
      console.log('⏭️ Skipping: Network or graphData not ready');
      return;
    }

    const nodes = network.body.data.nodes;
    if (!nodes) {
      console.log('⏭️ Skipping: Nodes DataSet not ready');
      return;
    }

    try {
      const allNodeIds = nodes.getIds();
      console.log(`🔄 Updating ${allNodeIds.length} total nodes, ${highlightedNodes.length} to highlight`);

      const updates = allNodeIds.map(nodeId => {
        const graphNode = graphData.nodes.find(n => n.id === nodeId);
        if (!graphNode) return null;

        const isHighlighted = highlightedNodes.includes(nodeId);
        const baseColor = isHighlighted
          ? { background: '#22d3ee', border: '#ffffff' }
          : getNodeColor(graphNode.type);

        return {
          id: nodeId,
          color: {
            background: baseColor.background,
            border: baseColor.border
          },
          font: {
            color: isHighlighted ? '#ffffff' : '#f4f4f5',
            strokeWidth: isHighlighted ? 3 : 0,
            strokeColor: isHighlighted ? '#000000' : undefined
          },
          shadow: isHighlighted ? {
            enabled: true,
            color: 'rgba(34, 211, 238, 0.6)',
            size: 30
          } : undefined
        };
      }).filter(Boolean);

      // FIX: Always update, even if highlightedNodes.length === 0 (clears old highlights)
      requestAnimationFrame(() => {
        nodes.update(updates);
        const highlightedCount = updates.filter(u => highlightedNodes.includes(u.id)).length;
        console.log(`✅ Canvas updated: ${highlightedCount} cyan, ${updates.length - highlightedCount} normal`);
      });
    } catch (err) {
      console.error('❌ Canvas update error:', err);
    }
  }, [highlightedNodes, network, graphData]);

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
      // MULTI-TENANT FIX: Don't fetch until we have a repo (prevents race condition)
      if (!currentRepoId) {
        console.log('⏭️ GRAPH: Waiting for currentRepoId (will retry when available)');
        return;
      }

      try {
        console.log('📡 GRAPH FETCH START:', { currentRepoId, browser: navigator.userAgent.split(' ').pop() });

        setLoadingState({ isLoading: true, message: 'Loading graph data...', progress: 10 });

        let data;
        let dataSource = 'none';

        // CHECK PRE-FETCHED: Use graph data loaded during Loading phase (instant load)
        // Data is LZ-string compressed to fit large graphs within sessionStorage quota
        // NOTE: May be empty on Chrome/Safari if sessionStorage quota was exceeded
        try {
          const compressedData = sessionStorage.getItem('visdep_prefetched_graph');
          if (compressedData) {
            console.log(`📦 Found pre-fetched data: ${(compressedData.length * 2 / 1024).toFixed(1)}KB compressed`);
            // Decompress LZ-string data (compressed in Loading.jsx)
            const decompressed = LZString.decompressFromUTF16(compressedData);
            if (decompressed) {
              const prefetched = JSON.parse(decompressed);
              // Validate: correct repo and fresh (within 5 minutes)
              const isFresh = Date.now() - prefetched.timestamp < 5 * 60 * 1000;
              const isCorrectRepo = prefetched.repo_id === currentRepoId;

              if (isFresh && isCorrectRepo && prefetched.data) {
                console.log('⚡ INSTANT LOAD: Using pre-fetched graph data');
                data = prefetched.data;
                dataSource = 'sessionStorage';
                // Clear after use (one-time optimization)
                sessionStorage.removeItem('visdep_prefetched_graph');
              } else {
                console.log(`⏭️ Pre-fetched data invalid: fresh=${isFresh}, correctRepo=${isCorrectRepo}`);
              }
            } else {
              console.warn('⚠️ LZString decompression returned null');
            }
          } else {
            console.log('📭 No pre-fetched data in sessionStorage (quota may have been exceeded)');
          }
        } catch (storageErr) {
          console.warn('⚠️ sessionStorage read/decompress failed:', storageErr.message);
          // Non-fatal: will try IndexedDB, then API
        }

        // TIER 2: Try IndexedDB (for mega repos that exceed sessionStorage quota)
        if (!data && graphStorage.isAvailable()) {
          try {
            console.log('📦 Checking IndexedDB for mega-repo cache...');
            const idbData = await graphStorage.load(currentRepoId);
            if (idbData) {
              console.log(`⚡ IndexedDB LOAD: Found cached graph (${idbData.nodes?.length || 0} nodes)`);
              data = idbData;
              dataSource = 'IndexedDB';
              // Clear after use (one-time optimization)
              graphStorage.clear(currentRepoId);
            } else {
              console.log('📭 No IndexedDB cache found');
            }
          } catch (idbErr) {
            console.warn('⚠️ IndexedDB read failed:', idbErr.message);
            // Non-fatal: will fall back to API
          }
        }

        // TIER 3: Fetch from API if no cached data
        // This ensures graph loads even when all caches fail
        if (!data) {
          const url = `/api/dependency_graph?repo_id=${currentRepoId}`;
          console.log('📡 API FALLBACK: Fetching from', url);
          const response = await API.get(url);
          data = response.data;
          dataSource = 'API';
          console.log(`✅ API fetch successful: ${data.nodes?.length || 0} nodes`);
        }

        console.log(`📊 GRAPH LOADED via ${dataSource}:`, {
          nodes: data.nodes?.length,
          edges: data.edges?.length,
          firstNode: data.nodes?.[0]?.id
        });
        setLoadingState({ isLoading: true, message: 'Analyzing graph structure...', progress: 30 });

        // Check for mega-repo warning from backend
        if (data.mega_repo_warning) {
          setMegaRepoWarning(data.mega_repo_warning);
          console.warn('⚠️ MEGA-REPO:', data.mega_repo_warning);
        }

        // =========================================================================
        // LOD FALLBACK: For mega-repos, show only nodes with positions
        // =========================================================================
        // For very large repos (>20K nodes), we compute positions only for file
        // structure (directories + files). This keeps the graph beautiful and fast.
        // Users can still ask questions about any code - RAG works on full chunks.
        //
        // Logic:
        // 1. If ALL nodes have positions → render all (full graph)
        // 2. If SOME nodes have positions → render only positioned nodes (file structure)
        // 3. If NO nodes have positions → filter to file structure (safety fallback)
        // =========================================================================
        const MEGA_REPO_THRESHOLD = 20000;
        const nodesWithPositions = data.nodes.filter(n => n.x !== undefined && n.y !== undefined);
        const positionedRatio = nodesWithPositions.length / data.nodes.length;

        if (data.nodes.length > MEGA_REPO_THRESHOLD) {
          if (positionedRatio > 0.9) {
            // >90% have positions: render all (full graph with positions)
            console.log(`✅ MEGA-REPO: ${data.nodes.length} nodes, ${(positionedRatio * 100).toFixed(0)}% have positions - rendering full graph`);
          } else if (nodesWithPositions.length > 0) {
            // Some have positions: render only positioned nodes (file structure)
            console.log(`📁 MEGA-REPO: ${data.nodes.length} nodes, only ${nodesWithPositions.length} have positions - showing file structure`);

            const positionedIds = new Set(nodesWithPositions.map(n => n.id));
            const filteredEdges = data.edges.filter(e =>
              positionedIds.has(e.source) && positionedIds.has(e.target)
            );

            setMegaRepoWarning({
              ...data.mega_repo_warning,
              message: `Showing file structure (${nodesWithPositions.length.toLocaleString()} nodes). Full codebase (${data.nodes.length.toLocaleString()} nodes) available for questions.`,
              lod_active: true
            });

            data = { ...data, nodes: nodesWithPositions, edges: filteredEdges };
          } else {
            // No positions: filter to file structure (safety fallback)
            console.warn(`⚠️ LOD FALLBACK: ${data.nodes.length} nodes without positions - filtering to file structure`);

            const structureTypes = new Set(['directory', 'file']);
            const filteredNodes = data.nodes.filter(n => structureTypes.has(n.type));
            const filteredNodeIds = new Set(filteredNodes.map(n => n.id));
            const filteredEdges = data.edges.filter(e =>
              filteredNodeIds.has(e.source) && filteredNodeIds.has(e.target)
            );

            setMegaRepoWarning({
              ...data.mega_repo_warning,
              message: `Showing file structure only (${filteredNodes.length.toLocaleString()} nodes). Full codebase (${data.nodes.length.toLocaleString()} nodes) available for questions.`,
              lod_active: true
            });

            data = { ...data, nodes: filteredNodes, edges: filteredEdges };
          }
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
  }, [currentRepoId]);  // Refetch when repo changes  // Only run once on mount - removed circular dependencies

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

  // eslint-disable-next-line no-unused-vars
  const handleSearch = (event) => {
    setSearchTerm(event.target.value);
  };

  // Search bar functionality
  const performSearch = useCallback((query) => {
    if (!graphData || !query.trim()) {
      setSearchResults([]);
      return;
    }

    const queryLower = query.toLowerCase();
    const results = graphData.nodes
      .filter(node => {
        const label = (node.label || '').toLowerCase();
        const id = (node.id || '').toLowerCase();
        return label.includes(queryLower) || id.includes(queryLower);
      })
      .slice(0, 10)  // Limit to 10 results
      .map(node => ({
        id: node.id,
        label: node.label || node.id,
        type: node.type
      }));

    setSearchResults(results);
    setSelectedResultIndex(-1);
  }, [graphData]);

  const handleSearchQueryChange = (e) => {
    const query = e.target.value;
    setSearchQuery(query);
    performSearch(query);
  };

  const handleSearchKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedResultIndex(prev => 
        prev < searchResults.length - 1 ? prev + 1 : prev
      );
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedResultIndex(prev => prev > 0 ? prev - 1 : -1);
    } else if (e.key === 'Enter' && selectedResultIndex >= 0 && searchResults[selectedResultIndex]) {
      e.preventDefault();
      handleNodeSelectFromSearch(searchResults[selectedResultIndex].id);
    } else if (e.key === 'Escape') {
      setSearchQuery('');
      setSearchResults([]);
      setIsSearchFocused(false);
      searchInputRef.current?.blur();
    }
  };

  const handleNodeSelectFromSearch = useCallback((nodeId) => {
    if (!network || !graphData) return;

    // Get node position
    const positions = network.getPositions([nodeId]);
    if (!positions[nodeId]) {
      // Node might not be visible yet, try to find it in graph data
      const node = graphData.nodes.find(n => n.id === nodeId);
      if (!node) return;
      
      // Fit to show all nodes, then zoom to this one
      network.fit({ animation: { duration: 400 } });
      
      // Try again after fit
      setTimeout(() => {
        const newPositions = network.getPositions([nodeId]);
        if (newPositions[nodeId]) {
          const pos = newPositions[nodeId];
          network.moveTo({
            position: { x: pos.x, y: pos.y },
            scale: 1.5,
            animation: { duration: 600, easingFunction: 'easeInOutQuad' }
          });
        }
      }, 450);
    } else {
      const pos = positions[nodeId];

      // Smooth camera transition to node
      network.moveTo({
        position: { x: pos.x, y: pos.y },
        scale: 1.5,  // Zoom in slightly
        animation: {
          duration: 600,
          easingFunction: 'easeInOutQuad'
        }
      });
    }

    // Pulse effect: temporarily highlight the node
    if (network.body && network.body.data) {
      const nodes = network.body.data.nodes;
      const nodeData = nodes.get(nodeId);
      
      if (nodeData) {
        // Store original properties
        const originalBackground = nodeData.color?.background || nodeData.color || '#18181b';
        const originalBorder = nodeData.color?.border || '#52525b';
        const originalSize = nodeData.size || 20;

        // Pulse with cyan glow
        nodes.update({
          id: nodeId,
          color: {
            background: '#22d3ee',
            border: '#ffffff',
            highlight: { background: '#22d3ee', border: '#ffffff' }
          },
          font: { color: '#000000' },
          size: originalSize * 1.3  // Slightly larger
        });

        // Dim other nodes temporarily
        const allNodeIds = graphData.nodes.map(n => n.id).filter(id => id !== nodeId);
        const updates = allNodeIds.map(id => {
          const node = nodes.get(id);
          return {
            id,
            opacity: 0.3,
            color: {
              ...node.color,
              opacity: 0.3
            }
          };
        });
        nodes.update(updates);

        // Restore after animation
        setTimeout(() => {
          nodes.update({
            id: nodeId,
            color: {
              background: originalBackground,
              border: originalBorder
            },
            size: originalSize
          });
          
          const restoreUpdates = allNodeIds.map(id => {
            const node = nodes.get(id);
            return {
              id,
              opacity: 1.0,
              color: {
                ...node.color,
                opacity: 1.0
              }
            };
          });
          nodes.update(restoreUpdates);
        }, 2000);

        // Call onNodeSelect callback if provided
        if (onNodeSelect) {
          const node = graphData.nodes.find(n => n.id === nodeId);
          if (node) {
            onNodeSelect({ id: nodeId, label: node.label, type: node.type }, null);
          }
        }
      }
    }

    // Clear search
    setSearchQuery('');
    setSearchResults([]);
    setIsSearchFocused(false);
    searchInputRef.current?.blur();
  }, [network, graphData, onNodeSelect]);

  // Cmd+K keyboard shortcut
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        searchInputRef.current?.focus();
        setIsSearchFocused(true);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

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

  // eslint-disable-next-line no-unused-vars
  const handleFitGraph = () => {
    if (network) {
      network.fit({ animation: { duration: 1000, easingFunction: 'easeOutQuart' } });
    }
  };

  // eslint-disable-next-line no-unused-vars
  const handleZoomIn = () => {
    if (network) {
      const scale = network.getScale() * 1.2;
      network.moveTo({ scale: scale });
    }
  };

  // eslint-disable-next-line no-unused-vars
  const handleZoomOut = () => {
    if (network) {
      const scale = network.getScale() / 1.2;
      network.moveTo({ scale: scale });
    }
  };

  // eslint-disable-next-line no-unused-vars
  const toggleFilter = () => {
    setIsFilterOpen(!isFilterOpen);
  };

  // Query node system handlers
  // eslint-disable-next-line no-unused-vars
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

  // eslint-disable-next-line no-unused-vars
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [network]);

  // Old functions removed - using HTML panels now

  // eslint-disable-next-line no-unused-vars
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
        file_path: node.id,  // chunk_id contains file path
        repo_id: currentRepoId  // Multi-tenant: Explicit repo for user isolation
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [network, currentRepoId]);

  // Panels are react-rnd managed, no position tracking needed

  // Close filter dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (isFilterOpen && !e.target.closest('.filter-dropdown-container')) {
        setIsFilterOpen(false);
      }
      // Close search dropdown when clicking outside
      if (searchQuery && !e.target.closest('.search-hud-container')) {
        setSearchQuery('');
        setSearchResults([]);
        setIsSearchFocused(false);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [isFilterOpen, searchQuery]);

  return (
    <div className="h-full flex flex-col relative">
      {/* Modern 2025 Toolbar */}
      {/* Search HUD - Top Center */}
      <div className="search-hud-container absolute top-6 left-1/2 -translate-x-1/2 z-20" style={{ width: '400px', maxWidth: '90vw' }}>
        <div className="relative">
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={handleSearchQueryChange}
            onKeyDown={handleSearchKeyDown}
            onFocus={() => setIsSearchFocused(true)}
            onBlur={() => setTimeout(() => setIsSearchFocused(false), 200)}  // Delay to allow click on results
            placeholder="// GOTO_NODE"
            className="w-full px-4 py-2.5 rounded-lg transition-all duration-200 outline-none"
            style={{
              backgroundColor: 'rgba(0, 0, 0, 0.4)',
              backdropFilter: 'blur(24px)',
              border: isSearchFocused ? '1px solid rgba(34, 211, 238, 0.5)' : '1px solid rgba(255, 255, 255, 0.1)',
              color: '#f4f4f5',
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '12px',
              boxShadow: isSearchFocused ? '0 0 0 3px rgba(34, 211, 238, 0.1)' : 'none'
            }}
          />
          {searchQuery && (
            <div className="absolute top-full mt-1 w-full rounded-lg overflow-hidden" style={{
              backgroundColor: 'rgba(0, 0, 0, 0.6)',
              backdropFilter: 'blur(24px)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              maxHeight: '300px',
              overflowY: 'auto'
            }}>
              {searchResults.length > 0 ? (
                searchResults.map((result, index) => (
                  <div
                    key={result.id}
                    onClick={() => handleNodeSelectFromSearch(result.id)}
                    className="px-4 py-2.5 cursor-pointer transition-all"
                    style={{
                      backgroundColor: selectedResultIndex === index ? 'rgba(34, 211, 238, 0.2)' : 'transparent',
                      borderLeft: selectedResultIndex === index ? '2px solid #22d3ee' : '2px solid transparent',
                      color: '#f4f4f5',
                      fontFamily: "'JetBrains Mono', monospace",
                      fontSize: '11px'
                    }}
                    onMouseEnter={() => setSelectedResultIndex(index)}
                  >
                    <div style={{ fontWeight: 500, marginBottom: '2px' }}>{result.label}</div>
                    <div style={{ color: '#71717a', fontSize: '10px', textTransform: 'uppercase' }}>{result.type}</div>
                  </div>
                ))
              ) : (
                <div className="px-4 py-2.5 text-center" style={{
                  color: '#71717a',
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: '11px'
                }}>
                  No results found
                </div>
              )}
            </div>
          )}
          {!searchQuery && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" style={{
              color: '#71717a',
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '10px'
            }}>
              ⌘K
            </div>
          )}
        </div>
      </div>

      {/* Floating Island Control - Top Center (below search) */}
      <div className="absolute top-20 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1.5 px-3 py-2 rounded-full" style={{
        backgroundColor: 'rgba(9, 9, 11, 0.4)',
        backdropFilter: 'blur(16px)',
        border: '1px solid rgba(255, 255, 255, 0.1)'
      }}>
        {/* Quick Filters - Segmented Control */}
        <button
          onClick={() => handleNodeTypeToggle('directory')}
          className="px-2 py-1 text-[10px] font-medium transition-all rounded-md"
          style={{
            backgroundColor: selectedNodeTypes['directory'] ? 'rgba(16, 185, 129, 0.2)' : 'transparent',
            color: selectedNodeTypes['directory'] ? '#10b981' : '#52525b',
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
            backgroundColor: selectedNodeTypes['method'] ? 'rgba(249, 115, 22, 0.2)' : 'transparent',
            color: selectedNodeTypes['method'] ? '#f97316' : '#52525b',
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
  directory: { border: '#10b981', background: '#18181b' },  // Emerald green (completes palette)
  file: { border: '#3b82f6', background: '#18181b' },  // Blue for files
  import: { border: '#52525b', background: '#18181b' },  // Muted
  package: { border: '#52525b', background: '#18181b' },  // Muted
  class_definition: { border: '#6366f1', background: '#18181b' },  // Indigo (matches blue vibrance)
  function: { border: '#eab308', background: '#18181b' },  // Yellow for functions (distinct from blue files)
  method: { border: '#f97316', background: '#18181b' },  // Orange (complements blue, distinct from class)
  module_variable: { border: '#52525b', background: '#18181b' },  // Muted
  default: { border: '#52525b', background: '#18181b' },  // Muted zinc gray
};

export default DependencyGraph;
