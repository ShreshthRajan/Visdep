import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';
import API from '../api';
import CodeNode from './nodes/CodeNode';
import FileNode from './nodes/FileNode';
import QueryNode from './nodes/QueryNode';
import AnswerNode from './nodes/AnswerNode';

/**
 * ReactFlowGraph - Custom graph visualization using ReactFlow
 *
 * Replaces vis-network with ReactFlow for:
 * - HTML-based nodes (fully interactive)
 * - Custom node types (Code, Query, Answer)
 * - Dagre auto-layout
 * - Better performance and flexibility
 */
// Register custom node types
const nodeTypes = {
  code: CodeNode,
  file: FileNode,
  directory: FileNode,
  query: QueryNode,
  answer: AnswerNode,
};

const ReactFlowGraph = ({ highlightedNodes = [] }) => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [contextMenu, setContextMenu] = useState(null);
  const [queryNodeCounter, setQueryNodeCounter] = useState(0);
  const [selectedNodeTypes, setSelectedNodeTypes] = useState({
    directory: true,
    file: true,
    import: true,
    package: true,
    class_definition: true,
    function: true,
    method: true,
    module_variable: true,
  });

  // Dagre layout configuration
  const dagreGraph = useMemo(() => {
    const g = new dagre.graphlib.Graph();
    g.setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: 'TB', nodesep: 100, ranksep: 150 });
    return g;
  }, []);

  // Simple grid layout for initial graph (fast, handles large graphs)
  const getSimpleLayout = useCallback((nodes) => {
    console.log('📐 SIMPLE LAYOUT: Positioning', nodes.length, 'nodes in grid');

    const cols = Math.ceil(Math.sqrt(nodes.length));
    const nodeWidth = 200;
    const nodeHeight = 100;

    return nodes.map((node, index) => {
      const col = index % cols;
      const row = Math.floor(index / cols);

      return {
        ...node,
        position: {
          x: col * nodeWidth,
          y: row * nodeHeight
        }
      };
    });
  }, []);

  // Dagre layout for query/answer nodes ONLY (small incremental updates)
  const layoutQuerySubtree = useCallback((allNodes, allEdges, newNodeIds) => {
    console.log('🎨 DAGRE SUBTREE: Layouting query nodes:', newNodeIds);

    // Only layout the query node and its children
    const subtreeNodes = allNodes.filter(n =>
      newNodeIds.includes(n.id) ||
      allEdges.some(e => newNodeIds.includes(e.source) && e.target === n.id)
    );

    if (subtreeNodes.length === 0) return { nodes: allNodes, edges: allEdges };

    const g = new dagre.graphlib.Graph();
    g.setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: 'TB', nodesep: 50, ranksep: 80 });

    subtreeNodes.forEach(node => {
      g.setNode(node.id, { width: node.width || 180, height: node.height || 80 });
    });

    allEdges
      .filter(e => subtreeNodes.some(n => n.id === e.source) && subtreeNodes.some(n => n.id === e.target))
      .forEach(edge => {
        g.setEdge(edge.source, edge.target);
      });

    dagre.layout(g);

    const layoutedNodes = allNodes.map(node => {
      if (subtreeNodes.some(n => n.id === node.id)) {
        const positioned = g.node(node.id);
        return {
          ...node,
          position: {
            x: positioned.x - (node.width || 180) / 2,
            y: positioned.y - (node.height || 80) / 2
          }
        };
      }
      return node;
    });

    return { nodes: layoutedNodes, edges: allEdges };
  }, []);

  // Fetch and convert graph data
  useEffect(() => {
    const fetchGraphData = async () => {
      try {
        setIsLoading(true);
        const response = await API.get('/api/dependency_graph');
        const data = response.data;

        console.log('📊 Fetched graph data:', {
          nodes: data.nodes?.length,
          edges: data.edges?.length || data.links?.length
        });

        // Convert vis-network format to ReactFlow format
        const rawEdges = data.edges || data.links || [];

        const reactFlowNodes = data.nodes
          .filter(node => selectedNodeTypes[node.type])
          .map(node => {
            // Determine node type for ReactFlow
            let nodeType = 'code';  // Default
            if (node.type === 'file') nodeType = 'file';
            if (node.type === 'directory') nodeType = 'directory';

            return {
              id: node.id,
              type: nodeType,
              data: {
                label: node.label || node.id,
                type: node.type,
                originalNode: node
              },
              position: { x: 0, y: 0 },  // Dagre will position
              width: nodeType === 'file' || nodeType === 'directory' ? 140 : 180,
              height: nodeType === 'file' || nodeType === 'directory' ? 50 : 80,
            };
          });

        // Create node ID set for edge validation
        const nodeIdSet = new Set(reactFlowNodes.map(n => n.id));

        const reactFlowEdges = rawEdges
          .filter(edge => {
            // Only include edges where both source and target nodes exist
            return nodeIdSet.has(edge.source) && nodeIdSet.has(edge.target);
          })
          .map(edge => ({
            id: edge.id || `${edge.source}-${edge.target}`,
            source: edge.source,
            target: edge.target,
            type: 'default',
            animated: edge.relation === 'imports',
            style: {
              stroke: getEdgeColor(edge.relation).color,
              strokeWidth: 1.5
            },
            markerEnd: {
              type: MarkerType.ArrowClosed,
              color: getEdgeColor(edge.relation).color
            }
          }));

        console.log('✅ Converted to ReactFlow format:', {
          nodes: reactFlowNodes.length,
          edges: reactFlowEdges.length
        });

        console.log('📐 Sample node:', reactFlowNodes[0]);
        console.log('📐 Sample edge:', reactFlowEdges[0]);

        // Use simple grid layout for initial load (fast for large graphs)
        console.log('🔄 Using simple grid layout for initial load...');
        const layoutedNodes = getSimpleLayout(reactFlowNodes);

        console.log('✅ Layout complete:', {
          nodes: layoutedNodes.length,
          edges: reactFlowEdges.length
        });
        console.log('📐 Sample positioned node:', layoutedNodes[0]);

        console.log('🎨 Setting nodes and edges in state...');
        setNodes(layoutedNodes);
        setEdges(reactFlowEdges);

        console.log('✅ State updated, setting isLoading = false');
        setIsLoading(false);

        console.log('✅ Graph ready with simple layout');
      } catch (error) {
        console.error('Error fetching graph:', error);
        setIsLoading(false);
      }
    };

    fetchGraphData();
  }, [selectedNodeTypes, getSimpleLayout]);

  // Create query node under parent
  const createQueryNode = useCallback((parentNode) => {
    const queryId = `query_${parentNode.id}_${Date.now()}`;

    const queryNode = {
      id: queryId,
      type: 'query',
      data: {
        parentId: parentNode.id,
        parentLabel: parentNode.data.label.split('\n')[0],
        conversation: [],
        isExpanded: true,
        onAnswer: handleQueryAnswer,
        onMinimize: handleQueryMinimize
      },
      position: { x: 0, y: 0 },
      width: 350,
      height: 180
    };

    const queryEdge = {
      id: `edge_${parentNode.id}_${queryId}`,
      source: parentNode.id,
      target: queryId,
      type: 'smoothstep',
      animated: false,
      style: { stroke: '#9CA3AF', strokeWidth: 2 }
    };

    // Add nodes and edges, then use Dagre to position ONLY the query node
    const newNodes = [...nodes, queryNode];
    const newEdges = [...edges, queryEdge];

    // Use Dagre for small subtree layout (query node positioning)
    const { nodes: layoutedNodes, edges: layoutedEdges } = layoutQuerySubtree(
      newNodes,
      newEdges,
      [queryId]
    );

    setNodes(layoutedNodes);
    setEdges(layoutedEdges);
    setContextMenu(null);

    console.log('✅ Created query node:', queryId);
  }, [nodes, edges, layoutQuerySubtree]);

  // Handle answer from query node
  const handleQueryAnswer = useCallback((queryId, question, answer) => {
    const answerId = `answer_${queryId}_${Date.now()}`;

    const answerNode = {
      id: answerId,
      type: 'answer',
      data: {
        question,
        answer,
        queryId
      },
      position: { x: 0, y: 0 },
      width: 350,
      height: 250
    };

    const answerEdge = {
      id: `edge_${queryId}_${answerId}`,
      source: queryId,
      target: answerId,
      type: 'smoothstep',
      animated: true,
      style: { stroke: '#10B981', strokeWidth: 2 }
    };

    const newNodes = [...nodes, answerNode];
    const newEdges = [...edges, answerEdge];

    // Use Dagre to position answer node under query
    const { nodes: layoutedNodes, edges: layoutedEdges } = layoutQuerySubtree(
      newNodes,
      newEdges,
      [answerId]
    );

    setNodes(layoutedNodes);
    setEdges(layoutedEdges);

    console.log('✅ Created answer node:', answerId);
  }, [nodes, edges, layoutQuerySubtree]);

  // Handle query node minimize
  const handleQueryMinimize = useCallback((queryId, conversation) => {
    // Update query node to minimized state
    setNodes(nds =>
      nds.map(node => {
        if (node.id === queryId) {
          return {
            ...node,
            data: {
              ...node.data,
              isExpanded: false,
              conversation
            },
            width: 60,
            height: 40
          };
        }
        return node;
      })
    );

    // Re-layout using Dagre (small update)
    setTimeout(() => {
      const { nodes: layoutedNodes, edges: layoutedEdges } = layoutQuerySubtree(nodes, edges, [queryId]);
      setNodes(layoutedNodes);
      setEdges(layoutedEdges);
    }, 100);
  }, [nodes, edges, layoutQuerySubtree]);

  // Handle node click
  const onNodeClick = useCallback((event, node) => {
    console.log('Node clicked:', node);
    setContextMenu(null);

    // If clicking minimized query node, expand it
    if (node.type === 'query' && node.data.isExpanded === false) {
      setNodes(nds =>
        nds.map(n => {
          if (n.id === node.id) {
            return {
              ...n,
              data: { ...n.data, isExpanded: true },
              width: 350,
              height: 180
            };
          }
          return n;
        })
      );

      setTimeout(() => {
        const { nodes: layoutedNodes, edges: layoutedEdges } = layoutQuerySubtree(nodes, edges, [node.id]);
        setNodes(layoutedNodes);
        setEdges(layoutedEdges);
      }, 100);
      return;
    }

    // Highlight connected edges
    const connectedEdges = edges.filter(
      edge => edge.source === node.id || edge.target === node.id
    );

    setEdges(eds =>
      eds.map(edge => {
        const isConnected = connectedEdges.some(ce => ce.id === edge.id);
        return {
          ...edge,
          style: {
            ...edge.style,
            stroke: isConnected ? '#10B981' : edge.style.stroke,
            strokeWidth: isConnected ? 2.5 : 1.5
          }
        };
      })
    );
  }, [edges, nodes, layoutQuerySubtree]);

  // Handle right-click for context menu
  const onNodeContextMenu = useCallback((event, node) => {
    event.preventDefault();

    // Only show context menu for code nodes (not query/answer nodes)
    if (node.type === 'query' || node.type === 'answer') return;

    setContextMenu({
      x: event.clientX,
      y: event.clientY,
      node
    });
  }, []);

  console.log('🎨 RENDER: isLoading =', isLoading, 'nodes =', nodes.length, 'edges =', edges.length);

  if (isLoading) {
    console.log('🔄 Showing loading screen...');
    return (
      <div className="flex items-center justify-center h-full" style={{ backgroundColor: 'var(--black)' }}>
        <div className="text-center">
          <div
            className="animate-spin rounded-full h-12 w-12 mb-4 mx-auto"
            style={{
              borderWidth: '3px',
              borderStyle: 'solid',
              borderColor: 'var(--border-default)',
              borderTopColor: 'var(--accent)'
            }}
          />
          <p style={{ color: 'var(--text-primary)' }}>Loading graph...</p>
        </div>
      </div>
    );
  }

  console.log('🎨 Rendering ReactFlow with:', { nodes: nodes.length, edges: edges.length, nodeTypes: Object.keys(nodeTypes) });

  return (
    <div style={{ width: '100%', height: '100%', backgroundColor: 'var(--black)' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onNodeContextMenu={onNodeContextMenu}
        onPaneClick={() => setContextMenu(null)}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.1}
        maxZoom={2}
        defaultEdgeOptions={{
          type: 'smoothstep',
        }}
        style={{ backgroundColor: 'var(--black)' }}
      >
        <Background color="var(--border-subtle)" gap={16} />
        <Controls
          style={{
            backgroundColor: 'var(--card-bg)',
            border: '1px solid var(--border-default)',
            borderRadius: '8px'
          }}
        />
        <MiniMap
          nodeColor={(node) => {
            const colors = getNodeColor(node.data.type);
            return colors.background;
          }}
          style={{
            backgroundColor: 'var(--card-bg)',
            border: '1px solid var(--border-default)',
            borderRadius: '8px'
          }}
        />
      </ReactFlow>

      {/* Context Menu */}
      {contextMenu && (
        <div
          style={{
            position: 'fixed',
            left: `${contextMenu.x}px`,
            top: `${contextMenu.y}px`,
            backgroundColor: 'var(--card-bg)',
            border: '1px solid var(--border-default)',
            borderRadius: '8px',
            boxShadow: '0 12px 48px rgba(0, 0, 0, 0.2)',
            zIndex: 1000,
            minWidth: '200px'
          }}
        >
          <button
            onClick={() => createQueryNode(contextMenu.node)}
            style={{
              width: '100%',
              textAlign: 'left',
              padding: '10px 16px',
              backgroundColor: 'transparent',
              border: 'none',
              cursor: 'pointer',
              fontFamily: "'Inter', sans-serif",
              fontSize: '13px',
              color: 'var(--text-primary)',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              transition: 'background-color 0.2s'
            }}
            onMouseEnter={(e) => e.target.style.backgroundColor = 'var(--elevated)'}
            onMouseLeave={(e) => e.target.style.backgroundColor = 'transparent'}
          >
            <span>💬</span>
            Ask about {contextMenu.node.data.label.split('\n')[0]}
          </button>
        </div>
      )}
    </div>
  );
};

// Helper functions (reused from old component)
const getNodeColor = (type) => {
  const colors = {
    directory: { border: '#4B5563', background: '#374151' },
    file: { border: '#4B5563', background: '#1F2937' },
    import: { border: '#10B981', background: '#065F46' },
    package: { border: '#10B981', background: '#064E3B' },
    class_definition: { border: '#8B5CF6', background: '#6B21A8' },
    function: { border: '#3B82F6', background: '#1E40AF' },
    method: { border: '#A855F7', background: '#7E22CE' },
    module_variable: { border: '#10B981', background: '#065F46' },
    default: { border: '#4B5563', background: '#374151' }
  };
  return colors[type] || colors.default;
};

const getEdgeColor = (relation) => {
  const colors = {
    contains: { color: '#4B5563', opacity: 0.5 },
    imports: { color: '#10B981', opacity: 0.7 },
    exports: { color: '#3B82F6', opacity: 0.7 },
    multiple: { color: '#F59E0B', opacity: 0.8 },
    default: { color: '#4B5563', opacity: 0.4 }
  };
  return colors[relation] || colors.default;
};

export default ReactFlowGraph;
