import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Network, DataSet } from 'vis-network/standalone';
import { useAuth } from '../contexts/AuthContext';
import API from '../api';
import LZString from 'lz-string';
import graphStorage from '../utils/graphStorage';

const Loading = () => {
  const [progress, setProgress] = useState(0);
  const [logs, setLogs] = useState([]);
  const [showFlash, setShowFlash] = useState(false);
  const networkRef = useRef(null);
  const networkInstance = useRef(null);
  const logContainerRef = useRef(null);
  const uploadStartedRef = useRef(false);  // Prevent redirect after upload starts
  const navigate = useNavigate();
  const { user, githubToken } = useAuth();

  // Get upload data from sessionStorage (synchronously available)
  const uploadData = JSON.parse(sessionStorage.getItem('visdep_upload') || '{}');
  const { repoUrl, subDirectory } = uploadData;
  const [eta, setEta] = useState(null);

  // Effect 1: Redirect if no repoUrl AND upload hasn't started
  useEffect(() => {
    if (!repoUrl && !uploadStartedRef.current) {
      navigate('/');
    }
  }, [repoUrl, navigate]);

  // Effect 2: Auto-scroll logs (runs on EVERY log change)
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  // Initialize ghost graph
  useEffect(() => {
    if (!networkRef.current || networkInstance.current) return;

    const container = networkRef.current;
    const data = {
      nodes: new DataSet([]),
      edges: new DataSet([])
    };

    const options = {
      layout: {
        randomSeed: 42,
        improvedLayout: false
      },
      physics: {
        enabled: true,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {
          gravitationalConstant: -50,
          centralGravity: 0.01,
          springLength: 100,
          damping: 0.8
        },
        stabilization: {
          enabled: true,
          iterations: 150
        }
      },
      nodes: {
        shape: 'dot',  // Circles for nervous system look
        size: 12,
        color: {
          background: 'rgba(34, 211, 238, 0.2)',  // Cyan ghost circles
          border: '#22d3ee'
        },
        font: {
          size: 9,
          face: 'JetBrains Mono',
          color: '#52525b'
        },
        borderWidth: 1
      },
      edges: {
        color: {
          color: 'rgba(34, 211, 238, 0.3)',  // Cyan connections
          opacity: 0.4
        },
        width: 1,
        smooth: {
          type: 'continuous',
          roundness: 0.3
        }
      },
      interaction: {
        dragNodes: false,
        dragView: false,
        zoomView: false
      }
    };

    networkInstance.current = new Network(container, data, options);
  }, []);

  // Effect 3: Upload with real-time SSE streaming (runs ONCE on mount)
  useEffect(() => {
    if (!repoUrl) return;  // Guard clause - already redirected by Effect 1

    // Mark upload as started - prevents redirect during navigation
    uploadStartedRef.current = true;

    const uploadRepo = async () => {
      const repoName = repoUrl.split('/').pop() || 'repository';

      try {
        // Build upload payload
        const uploadPayload = {
          repo_url: repoUrl,
          sub_directory: subDirectory || null
        };

        if (user && user.id) {
          uploadPayload.user_id = user.id;
        }

        if (githubToken) {
          uploadPayload.github_token = githubToken;
        }

        // Use EventSource for SSE streaming
        // Note: EventSource doesn't support POST, so we'll use fetch with streaming
        const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000';
        const response = await fetch(`${apiUrl}/api/upload_repo_stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(uploadPayload)
        });

        if (!response.ok) {
          throw new Error(`Upload failed: ${response.statusText}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        // Node tracking for ghost graph (use object to avoid closure issues in loops)
        const counters = { node: 0 };
        const addedNodes = new Set();

        // Read SSE stream
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Split by SSE delimiter (double newline)
          const lines = buffer.split('\n\n');
          buffer = lines.pop() || ''; // Keep incomplete line in buffer

          for (const line of lines) {
            if (!line.trim() || !line.startsWith('data: ')) continue;

            try {
              const jsonData = line.substring(6); // Remove 'data: ' prefix
              const event = JSON.parse(jsonData);

              // Update progress
              if (event.progress !== undefined) {
                setProgress(event.progress);
              }

              // Handle different event types
              switch (event.type) {
                case 'init':
                  setLogs(prev => [...prev, `[INIT]: ${event.message}`]);
                  break;

                case 'preindexed':
                  setLogs(prev => [...prev, `[CACHED]: ${event.message}`]);
                  setLogs(prev => [...prev, `-> ${event.chunks.toLocaleString()} chunks ready`]);
                  setLogs(prev => [...prev, `-> ${event.nodes.toLocaleString()} nodes in graph`]);
                  break;

                case 'clone':
                  setLogs(prev => [...prev, `[GIT]: ${event.message}`]);
                  break;

                case 'clone_done':
                  setLogs(prev => [...prev, `-> Found ${event.file_count} files`]);

                  // Calculate ETA based on file count
                  // Based on benchmarks: parse ~2s/1000files, chunk ~5s/1000files, store ~3s/10K chunks
                  // Layout varies by node count (handled separately)
                  const estimateTotalTime = (fileCount) => {
                    if (fileCount < 500) return 30;
                    if (fileCount < 1000) return 60;
                    if (fileCount < 3000) return 120;
                    if (fileCount < 7000) return 240;
                    if (fileCount < 15000) return 420;  // ~7 min for 10K+ files
                    return 600;  // 10 min for mega-repos
                  };
                  const totalEta = estimateTotalTime(event.file_count);
                  setEta(totalEta);
                  setLogs(prev => [...prev, `-> Estimated processing time: ~${Math.round(totalEta / 60)} min`]);

                  // Add root node for actual repo
                  if (networkInstance.current && !addedNodes.has('root')) {
                    const nodesDataSet = networkInstance.current.body.data.nodes;
                    nodesDataSet.add({ id: 'root', label: repoName, x: 0, y: 0 });
                    addedNodes.add('root');
                  }

                  // Add sample files to graph
                  if (event.sample_files && networkInstance.current) {
                    const nodesDataSet = networkInstance.current.body.data.nodes;
                    const edgesDataSet = networkInstance.current.body.data.edges;

                    event.sample_files.slice(0, 5).forEach((filePath, idx) => {
                      const fileName = filePath.split('/').pop();
                      const nodeId = `file_${counters.node++}`;

                      if (!addedNodes.has(nodeId)) {
                        const angle = (idx / 5) * Math.PI * 2;
                        const radius = 120;
                        nodesDataSet.add({
                          id: nodeId,
                          label: fileName,
                          x: Math.cos(angle) * radius,
                          y: Math.sin(angle) * radius
                        });
                        edgesDataSet.add({
                          id: `edge_root_${nodeId}`,
                          from: 'root',
                          to: nodeId
                        });
                        addedNodes.add(nodeId);
                      }
                    });
                  }
                  break;

                case 'filter':
                  setLogs(prev => [...prev, `[FILTER]: ${event.message}`]);
                  break;

                case 'filter_done':
                  if (event.excluded_dirs && event.excluded_dirs.length > 0) {
                    setLogs(prev => [...prev, `-> Filtered to ${event.filtered_count} files (excluded: ${event.excluded_dirs.join(', ')})`]);
                  } else {
                    setLogs(prev => [...prev, `-> ${event.filtered_count} files after filtering`]);
                  }
                  break;

                case 'parse':
                  setLogs(prev => [...prev, `[AST]: ${event.message}`]);
                  break;

                case 'parse_done':
                  setLogs(prev => [...prev, `-> Parsed ${event.parsed_count} files`]);
                  break;

                case 'store':
                  setLogs(prev => [...prev, `[DB]: ${event.message}`]);
                  break;

                case 'chunks':
                  setLogs(prev => [...prev, `[CHUNK]: ${event.message}`]);
                  break;

                case 'chunk_progress':
                  // Progress update during chunking - keeps UI alive for mega-repos
                  // Show more frequent updates for better UX on long operations
                  if (event.processed_files && event.total_files) {
                    const pct = Math.round((event.processed_files / event.total_files) * 100);
                    // Update log every 10% milestone for better visibility
                    if (pct % 10 === 0 && pct > 0 && pct < 100) {
                      setLogs(prev => [...prev, `-> Chunking: ${pct}% (${event.processed_files.toLocaleString()}/${event.total_files.toLocaleString()} files, ${event.chunks_so_far?.toLocaleString() || '?'} chunks)`]);
                    }
                  }
                  break;

                case 'chunks_done':
                  setLogs(prev => [...prev, `-> Generated ${event.chunk_count.toLocaleString()} chunks`]);
                  if (event.by_type) {
                    const typeStr = Object.entries(event.by_type)
                      .slice(0, 3)
                      .map(([type, count]) => `${type}:${count}`)
                      .join(', ');
                    setLogs(prev => [...prev, `-> Types: ${typeStr}`]);
                  }
                  break;

                case 'store_chunks':
                  setLogs(prev => [...prev, `[DB]: ${event.message}`]);
                  break;

                case 'graph':
                  setLogs(prev => [...prev, `[GRAPH]: ${event.message}`]);
                  break;

                case 'graph_done':
                  setLogs(prev => [...prev, `-> Created ${event.node_count.toLocaleString()} nodes, ${event.edge_count.toLocaleString()} edges`]);

                  // Add sample nodes from actual graph to visualization
                  if (event.sample_nodes && networkInstance.current) {
                    const nodesDataSet = networkInstance.current.body.data.nodes;
                    const edgesDataSet = networkInstance.current.body.data.edges;

                    event.sample_nodes.forEach((node, idx) => {
                      const nodeId = `graph_${node.id}`;

                      if (!addedNodes.has(nodeId)) {
                        const angle = ((idx + 5) / 10) * Math.PI * 2;
                        const radius = 200;
                        nodesDataSet.add({
                          id: nodeId,
                          label: node.label,
                          x: Math.cos(angle) * radius,
                          y: Math.sin(angle) * radius
                        });

                        // Connect to root or random existing node
                        const existingNodes = Array.from(addedNodes);
                        const randomExisting = existingNodes[Math.floor(Math.random() * existingNodes.length)];
                        edgesDataSet.add({
                          id: `edge_${randomExisting}_${nodeId}`,
                          from: randomExisting,
                          to: nodeId
                        });
                        addedNodes.add(nodeId);
                      }
                    });
                  }
                  break;

                case 'layout_info':
                  // Backend skips layout - will be computed on frontend with ForceAtlas2
                  setLogs(prev => [...prev, `[LAYOUT]: ${event.message}`]);
                  break;

                case 'link':
                  setLogs(prev => [...prev, `[ACCOUNT]: ${event.message}`]);
                  break;

                case 'done':
                  setLogs(prev => [...prev, `[COMPLETE]: ${event.message}`]);
                  setLogs(prev => [...prev, `-> Chunks: ${event.chunks.toLocaleString()}`]);
                  setLogs(prev => [...prev, `-> Nodes: ${event.node_count.toLocaleString()}`]);

                  // Fetch user repos for currentRepo state
                  let repoId = event.repo_id;
                  if (user) {
                    try {
                      const userReposResponse = await API.get(`/api/user/${user.id}/repos`);
                      const repos = userReposResponse.data;

                      if (repos && repos.length > 0) {
                        const justUploaded = repos[0];
                        // Try sessionStorage with fallback (Chrome/Safari may have quota issues)
                        try {
                          sessionStorage.setItem('visdep_current_repo', JSON.stringify(justUploaded));
                        } catch (storageErr) {
                          console.warn('⚠️ sessionStorage quota exceeded for repo metadata:', storageErr.message);
                          // Non-fatal: URL param fallback will be used
                        }
                        repoId = justUploaded.local_repo_id;
                      }
                    } catch (err) {
                      console.error('⚠️ Could not fetch uploaded repo:', err);
                    }
                  }

                  // PRE-FETCH GRAPH + COMPUTE FORCEATLAS2 LAYOUT
                  // This ensures GraphChat shows immediately with beautiful positioned graph
                  if (repoId) {
                    setLogs(prev => [...prev, `[GRAPH]: Pre-loading graph data...`]);
                    try {
                      const graphResponse = await API.get(`/api/dependency_graph?repo_id=${repoId}`);
                      let graphData = graphResponse.data;
                      const nodeCount = graphData.nodes?.length || 0;

                      // Check if nodes have pre-computed positions
                      const hasPositions = graphData.nodes?.some(n => n.x !== undefined && n.y !== undefined);

                      // =================================================================
                      // FORCEATLAS2 LAYOUT: Compute beautiful positions on Loading page
                      // =================================================================
                      // ForceAtlas2 is WebGL-accelerated and produces beautiful radial
                      // clustering layouts. This runs here so user waits on Loading page
                      // (not on graph-chat page). Positions are saved for instant future loads.
                      // =================================================================
                      if (!hasPositions && nodeCount > 0) {
                        // Estimate layout time for ETA display
                        const getLayoutETA = (count) => {
                          if (count < 500) return 5;
                          if (count < 1000) return 10;
                          if (count < 3000) return 20;
                          if (count < 8000) return 45;
                          if (count < 15000) return 90;
                          return 150;
                        };
                        const estimatedSeconds = getLayoutETA(nodeCount);
                        setEta(estimatedSeconds);
                        setLogs(prev => [...prev, `[LAYOUT]: Computing ForceAtlas2 layout (~${estimatedSeconds}s)...`]);

                        // Apply LOD filtering for mega-repos (>20K nodes)
                        // Show only file structure to keep layout fast
                        const MEGA_THRESHOLD = 20000;
                        let layoutNodes = graphData.nodes;
                        let layoutEdges = graphData.edges;

                        if (nodeCount > MEGA_THRESHOLD) {
                          const structureTypes = new Set(['directory', 'file']);
                          layoutNodes = graphData.nodes.filter(n => structureTypes.has(n.type));
                          const layoutNodeIds = new Set(layoutNodes.map(n => n.id));
                          layoutEdges = graphData.edges.filter(e =>
                            layoutNodeIds.has(e.source) && layoutNodeIds.has(e.target)
                          );
                          setLogs(prev => [...prev, `-> Mega-repo: layouting ${layoutNodes.length.toLocaleString()} file nodes`]);
                        }

                        // Get iterations based on node count (adaptive for performance)
                        const getIterations = (count) => {
                          if (count < 200) return 300;
                          if (count < 500) return 500;
                          if (count < 1000) return 800;
                          if (count < 3000) return 1000;
                          if (count < 8000) return 1200;
                          return 1500;
                        };
                        const iterations = getIterations(layoutNodes.length);

                        // Adaptive ForceAtlas2 parameters based on repo size
                        // Larger repos need tighter clustering to avoid sprawling hairballs
                        const getForceAtlas2Params = (count) => {
                          if (count < 1000) {
                            // Small repos: spread out, beautiful radial layout
                            return {
                              gravitationalConstant: -150,
                              centralGravity: 0.005,
                              springLength: 150,
                              springConstant: 0.04,
                              damping: 0.6,
                              avoidOverlap: 1.5,
                            };
                          } else if (count < 5000) {
                            // Medium repos: slightly tighter
                            return {
                              gravitationalConstant: -120,
                              centralGravity: 0.012,
                              springLength: 120,
                              springConstant: 0.05,
                              damping: 0.5,
                              avoidOverlap: 1.2,
                            };
                          } else if (count < 15000) {
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
                        const forceAtlas2Params = getForceAtlas2Params(layoutNodes.length);

                        // Create hidden container for layout computation
                        const layoutContainer = document.createElement('div');
                        layoutContainer.style.cssText = 'position:absolute;left:-9999px;width:1920px;height:1080px;';
                        document.body.appendChild(layoutContainer);

                        // Prepare vis-network data
                        const visNodes = new DataSet(layoutNodes.map(node => ({
                          id: node.id,
                          label: node.label || node.name || node.id,
                        })));

                        const visEdges = new DataSet(layoutEdges.map((edge, idx) => ({
                          id: `e${idx}`,
                          from: edge.source,
                          to: edge.target,
                        })));

                        // ForceAtlas2 options - adaptive based on repo size
                        const layoutOptions = {
                          layout: { randomSeed: 42 },
                          physics: {
                            enabled: true,
                            solver: 'forceAtlas2Based',
                            forceAtlas2Based: forceAtlas2Params,
                            stabilization: {
                              enabled: true,
                              iterations: iterations,
                              updateInterval: 50,
                              fit: true,
                            },
                          },
                          nodes: { shape: 'dot', size: 10 },
                          edges: { smooth: false },
                        };

                        // Create network and compute layout
                        const layoutNetwork = new Network(
                          layoutContainer,
                          { nodes: visNodes, edges: visEdges },
                          layoutOptions
                        );

                        // Wait for stabilization with progress updates
                        await new Promise((resolve) => {
                          let lastProgress = 0;

                          layoutNetwork.on('stabilizationProgress', (params) => {
                            const pct = Math.round((params.iterations / params.total) * 100);
                            if (pct >= lastProgress + 20) {
                              setLogs(prev => [...prev, `-> Stabilizing: ${pct}%`]);
                              lastProgress = pct;
                            }
                          });

                          layoutNetwork.once('stabilizationIterationsDone', () => {
                            setLogs(prev => [...prev, `-> Layout complete!`]);
                            resolve();
                          });

                          // Fallback timeout (shouldn't hit this normally)
                          setTimeout(() => {
                            console.warn('Layout timeout - proceeding anyway');
                            resolve();
                          }, estimatedSeconds * 1500); // 1.5x estimated time as safety
                        });

                        // Extract positions from network
                        const positions = layoutNetwork.getPositions();

                        // =====================================================================
                        // POSITION SCALE NORMALIZATION: Prevent GPU overdraw on mega-repos
                        // =====================================================================
                        // ForceAtlas2 creates tight clusters for large repos, causing high
                        // node density that freezes during zoom/pan (GPU overdraw).
                        //
                        // Solution: Normalize to target density of ~20 nodes per million unit²
                        // (matching Kubernetes which renders smoothly with 18K nodes).
                        //
                        // This does NOT affect graph beauty - relative positions are preserved,
                        // just scaled to optimal density for rendering performance.
                        // =====================================================================
                        const TARGET_DENSITY = 20; // nodes per million unit² (Kubernetes baseline)
                        const positionValues = Object.values(positions);

                        if (positionValues.length > 0) {
                          // Use loop instead of spread operator to avoid stack overflow on large arrays (60K+ nodes)
                          let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
                          for (const p of positionValues) {
                            if (p.x < minX) minX = p.x;
                            if (p.x > maxX) maxX = p.x;
                            if (p.y < minY) minY = p.y;
                            if (p.y > maxY) maxY = p.y;
                          }

                          const currentSpanX = maxX - minX || 1;
                          const currentSpanY = maxY - minY || 1;
                          const currentArea = currentSpanX * currentSpanY;
                          const currentDensity = (positionValues.length / currentArea) * 1e6;

                          // Calculate target span based on optimal density
                          const targetArea = (positionValues.length / TARGET_DENSITY) * 1e6;
                          const targetSpan = Math.sqrt(targetArea);

                          // Only scale if density is too high (>1.5x target)
                          if (currentDensity > TARGET_DENSITY * 1.5) {
                            const scaleFactor = targetSpan / Math.max(currentSpanX, currentSpanY);

                            // Center positions around origin, then scale
                            const centerX = (minX + maxX) / 2;
                            const centerY = (minY + maxY) / 2;

                            for (const nodeId of Object.keys(positions)) {
                              positions[nodeId].x = (positions[nodeId].x - centerX) * scaleFactor;
                              positions[nodeId].y = (positions[nodeId].y - centerY) * scaleFactor;
                            }

                            const newDensity = (positionValues.length / (targetSpan * targetSpan)) * 1e6;
                            setLogs(prev => [...prev, `-> Optimizing layout density for smooth rendering...`]);
                          } else {
                          }
                        }

                        // Apply positions to graph data
                        const positionsMap = {};
                        for (const [nodeId, pos] of Object.entries(positions)) {
                          positionsMap[nodeId] = { x: pos.x, y: pos.y };
                        }

                        // Update nodes with positions
                        graphData = {
                          ...graphData,
                          nodes: graphData.nodes.map(node => {
                            if (positionsMap[node.id]) {
                              return { ...node, x: positionsMap[node.id].x, y: positionsMap[node.id].y };
                            }
                            return node;
                          })
                        };

                        // Cleanup
                        layoutNetwork.destroy();
                        document.body.removeChild(layoutContainer);

                        // Save positions to backend for instant future loads
                        setLogs(prev => [...prev, `-> Saving ${Object.keys(positionsMap).length.toLocaleString()} positions...`]);
                        try {
                          await API.post('/api/save_graph_positions', {
                            repo_id: repoId,
                            positions: positionsMap
                          });
                          setLogs(prev => [...prev, `-> Positions saved!`]);
                        } catch (saveErr) {
                          console.warn('⚠️ Failed to save positions:', saveErr);
                          // Non-fatal - graph still works, just won't be cached
                        }

                        setEta(null);
                      } else if (hasPositions) {
                        setLogs(prev => [...prev, `-> Using cached positions`]);

                        // =====================================================================
                        // DENSITY CHECK FOR CACHED POSITIONS: Fix for pre-normalized repos
                        // =====================================================================
                        // Repos indexed before position normalization may have high density.
                        // Check and normalize if needed (same logic as fresh layout).
                        // =====================================================================
                        const nodesWithPositions = graphData.nodes.filter(n => n.x !== undefined && n.y !== undefined);
                        if (nodesWithPositions.length > 1000) { // Only check for large repos
                          const TARGET_DENSITY = 20; // nodes per million unit²

                          // Use reduce instead of spread operator to avoid stack overflow on large arrays (60K+ nodes)
                          let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
                          for (const node of nodesWithPositions) {
                            if (node.x < minX) minX = node.x;
                            if (node.x > maxX) maxX = node.x;
                            if (node.y < minY) minY = node.y;
                            if (node.y > maxY) maxY = node.y;
                          }

                          const currentSpanX = maxX - minX || 1;
                          const currentSpanY = maxY - minY || 1;
                          const currentArea = currentSpanX * currentSpanY;
                          const currentDensity = (nodesWithPositions.length / currentArea) * 1e6;

                          // Normalize if density exceeds 1.5x target (same threshold as fresh layout)
                          if (currentDensity > TARGET_DENSITY * 1.5) {
                            setLogs(prev => [...prev, `-> Optimizing cached layout density...`]);

                            const targetArea = (nodesWithPositions.length / TARGET_DENSITY) * 1e6;
                            const targetSpan = Math.sqrt(targetArea);
                            const scaleFactor = targetSpan / Math.max(currentSpanX, currentSpanY);

                            const centerX = (minX + maxX) / 2;
                            const centerY = (minY + maxY) / 2;

                            // Apply normalization to graphData nodes
                            graphData = {
                              ...graphData,
                              nodes: graphData.nodes.map(node => {
                                if (node.x !== undefined && node.y !== undefined) {
                                  return {
                                    ...node,
                                    x: (node.x - centerX) * scaleFactor,
                                    y: (node.y - centerY) * scaleFactor
                                  };
                                }
                                return node;
                              })
                            };

                            const newDensity = (nodesWithPositions.length / (targetSpan * targetSpan)) * 1e6;
                            setLogs(prev => [...prev, `-> Density optimized for smooth rendering`]);

                            // Save normalized positions back to backend for future loads
                            const normalizedPositions = {};
                            graphData.nodes.forEach(node => {
                              if (node.x !== undefined && node.y !== undefined) {
                                normalizedPositions[node.id] = { x: node.x, y: node.y };
                              }
                            });

                            API.post('/api/save_graph_positions', {
                              repo_id: repoId,
                              positions: normalizedPositions
                            }).then(() => {
                            }).catch(err => {
                              console.warn(`⚠️ Failed to save normalized positions: ${err.message}`);
                            });
                          } else {
                          }
                        }
                      }

                      // Compress and store graph data with tiered fallback:
                      // 1. sessionStorage (fast, 5MB limit)
                      // 2. IndexedDB (slower, 50MB+ limit for mega repos)
                      // 3. API fallback (slowest, always works)
                      const payload = JSON.stringify({
                        data: graphData,
                        repo_id: repoId,
                        timestamp: Date.now()
                      });
                      const compressed = LZString.compressToUTF16(payload);
                      const compressedSizeMB = (compressed.length * 2 / 1024 / 1024).toFixed(2);

                      let storageUsed = 'none';

                      // Try sessionStorage first (fast, but 5MB limit on Chrome/Safari)
                      try {
                        sessionStorage.setItem('visdep_prefetched_graph', compressed);
                        const compressionRatio = ((1 - compressed.length * 2 / payload.length) * 100).toFixed(1);
                        storageUsed = 'sessionStorage';
                      } catch (storageErr) {
                        // QuotaExceededError - try IndexedDB for mega repos
                        console.warn(`⚠️ sessionStorage quota exceeded (${compressedSizeMB}MB), trying IndexedDB...`);

                        // IndexedDB fallback for large graphs (50MB+ capacity)
                        if (graphStorage.isAvailable()) {
                          try {
                            await graphStorage.save(repoId, graphData);
                            setLogs(prev => [...prev, `-> Mega-repo: using IndexedDB cache`]);
                            storageUsed = 'indexedDB';
                          } catch (idbErr) {
                            console.warn(`⚠️ IndexedDB save failed: ${idbErr.message}`);
                            setLogs(prev => [...prev, `-> Large graph: using API fallback`]);
                          }
                        } else {
                          console.warn('⚠️ IndexedDB not available, will use API fallback');
                          setLogs(prev => [...prev, `-> Large graph: using API fallback`]);
                        }
                      }

                      setLogs(prev => [...prev, `-> Graph ready: ${nodeCount.toLocaleString()} nodes`]);

                    } catch (err) {
                      console.warn('⚠️ Graph pre-fetch failed, will load on page:', err);
                      setEta(null);
                      // Non-fatal: GraphChat will fetch if needed
                    }
                  }

                  // White-out flash transition
                  await new Promise(resolve => setTimeout(resolve, 400));
                  setShowFlash(true);
                  await new Promise(resolve => setTimeout(resolve, 500));

                  // Navigate to graph with repo_id in URL (primary source, sessionStorage is fallback)
                  // This ensures graph loads even if sessionStorage quota is exceeded
                  navigate(repoId ? `/graph-chat?repo_id=${repoId}` : '/graph-chat');
                  break;

                case 'error':
                  setLogs(prev => [...prev, `[ERROR]: ${event.message}`]);
                  setLogs(prev => [...prev, `[ERROR]: Upload failed. Please try again.`]);
                  setEta(null);
                  break;

                default:
                  console.warn('Unknown event type:', event.type);
              }

            } catch (parseError) {
              console.error('Error parsing SSE event:', parseError);
            }
          }
        }

      } catch (error) {
        console.error('Upload error:', error);
        setLogs(prev => [...prev, `[ERROR]: ${error.message || 'Upload failed'}`]);
        setLogs(prev => [...prev, `[ERROR]: Please check your connection and try again.`]);
      }
    };

    uploadRepo();
  }, [repoUrl, subDirectory, navigate, user, githubToken]);

  return (
    <div
      className="relative w-screen h-screen overflow-hidden"
      style={{ backgroundColor: '#050505' }}
    >
      {/* White-Out Flash Transition */}
      {showFlash && (
        <div
          className="absolute inset-0 z-50 animate-flash"
          style={{
            backgroundColor: '#ffffff',
            animation: 'flash 0.5s cubic-bezier(0.4, 0, 0.2, 1) forwards'
          }}
        />
      )}
      {/* Split Screen Layout */}
      <div className="flex h-full">
        {/* Left: Ghost Graph (60%) */}
        <div className="w-[60%] relative">
          <div ref={networkRef} className="absolute inset-0" />

          {/* Razor-thin Progress Line at Top */}
          <div className="absolute top-0 left-0 right-0 h-0.5 bg-zinc-900">
            <div
              className="h-full transition-all duration-300"
              style={{
                width: `${progress}%`,
                backgroundColor: '#22d3ee',
                boxShadow: '0 0 8px rgba(34, 211, 238, 0.6)'
              }}
            />
          </div>
        </div>

        {/* Right: Terminal Log (40%) */}
        <div
          className="w-[40%] relative"
          style={{
            backgroundColor: 'rgba(9, 9, 11, 0.8)',
            backdropFilter: 'blur(48px) saturate(180%)',
            borderLeft: '1px solid rgba(255, 255, 255, 0.1)'
          }}
        >
          {/* Log Header */}
          <div
            className="px-6 py-4"
            style={{
              borderBottom: '1px solid rgba(255, 255, 255, 0.05)'
            }}
          >
            <div
              className="text-xs font-medium"
              style={{
                color: '#71717a',
                fontFamily: "'JetBrains Mono', monospace",
                textTransform: 'uppercase',
                letterSpacing: '0.8px'
              }}
            >
              &gt; System Log
            </div>
          </div>

          {/* Log Stream */}
          <div
            ref={logContainerRef}
            className="overflow-y-auto px-6 py-4"
            style={{ height: 'calc(100% - 140px)' }}
          >
            {logs.map((log, index) => (
              <div
                key={index}
                className="mb-1 animate-fade-in"
                style={{
                  fontSize: '12px',
                  color: log.includes('[ERROR]') ? '#ef4444' : '#a1a1aa',
                  fontFamily: "'JetBrains Mono', monospace",
                  lineHeight: '1.6',
                  opacity: 0,
                  animation: 'fadeIn 0.3s ease forwards'
                }}
              >
                {log}
              </div>
            ))}

            {/* Blinking Cursor */}
            {progress < 100 && (
              <div
                className="inline-block w-2 h-4 ml-1 animate-pulse"
                style={{
                  backgroundColor: '#22d3ee',
                  animation: 'blink 1s step-end infinite'
                }}
              />
            )}
          </div>

          {/* Status Indicator - Minimal */}
          <div className="absolute bottom-8 left-1/2 -translate-x-1/2">
            <div
              className="px-5 py-2 rounded-md"
              style={{
                backgroundColor: 'rgba(24, 24, 27, 0.95)',
                backdropFilter: 'blur(16px)',
                border: '1px solid rgba(34, 211, 238, 0.2)'
              }}
            >
              <div
                className="text-xs font-medium"
                style={{
                  color: '#22d3ee',
                  fontFamily: "'JetBrains Mono', monospace",
                  letterSpacing: '0.02em'
                }}

              >
                {progress < 100
                  ? eta
                    ? `processing... ${progress}% (eta ${eta >= 60 ? `${Math.round(eta / 60)}m` : `${eta}s`})`
                    : `processing... ${progress}%`
                  : 'finishing...'}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Animations */}
      <style>{`
        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(4px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        @keyframes blink {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }

        @keyframes flash {
          0% {
            opacity: 0;
          }
          50% {
            opacity: 1;
          }
          100% {
            opacity: 0;
          }
        }
      `}</style>
    </div>
  );
};

export default Loading;
