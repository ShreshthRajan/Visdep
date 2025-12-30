import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Network, DataSet } from 'vis-network/standalone';
import { useAuth } from '../contexts/AuthContext';
import API from '../api';

const Loading = () => {
  const [progress, setProgress] = useState(0);
  const [logs, setLogs] = useState([]);
  const [currentStep, setCurrentStep] = useState('Initializing...');
  const [ghostNodes, setGhostNodes] = useState([]);
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
      let eventSource = null;

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

        // Node tracking for ghost graph
        let nodeCounter = 0;
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
                      const nodeId = `file_${nodeCounter++}`;

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

                case 'positions':
                  setLogs(prev => [...prev, `[LAYOUT]: ${event.message}`]);
                  setEta(120);  // Show 2 min ETA for position computation
                  break;

                case 'positions_progress':
                  setLogs(prev => [...prev, `-> ${event.message}`]);
                  break;

                case 'positions_done':
                  setLogs(prev => [...prev, `-> Saved ${event.positions_count.toLocaleString()} positions`]);
                  setEta(null);
                  break;

                case 'positions_skipped':
                  setLogs(prev => [...prev, `-> ${event.message}`]);
                  setEta(null);
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
                        sessionStorage.setItem('visdep_current_repo', JSON.stringify(justUploaded));
                        repoId = justUploaded.local_repo_id;
                      }
                    } catch (err) {
                      console.error('⚠️ Could not fetch uploaded repo:', err);
                    }
                  }

                  // PRE-FETCH GRAPH: Load graph data before navigating (eliminates 20s gap)
                  // This ensures GraphChat shows immediately with graph ready
                  if (repoId) {
                    setLogs(prev => [...prev, `[GRAPH]: Pre-loading graph data...`]);
                    try {
                      const graphResponse = await API.get(`/api/dependency_graph?repo_id=${repoId}`);
                      sessionStorage.setItem('visdep_prefetched_graph', JSON.stringify({
                        data: graphResponse.data,
                        repo_id: repoId,
                        timestamp: Date.now()
                      }));
                      setLogs(prev => [...prev, `-> Graph ready: ${graphResponse.data.nodes?.length?.toLocaleString() || 0} nodes`]);
                    } catch (err) {
                      console.warn('⚠️ Graph pre-fetch failed, will load on page:', err);
                      // Non-fatal: GraphChat will fetch if needed
                    }
                  }

                  // White-out flash transition
                  await new Promise(resolve => setTimeout(resolve, 400));
                  setShowFlash(true);
                  await new Promise(resolve => setTimeout(resolve, 500));

                  // Navigate to graph
                  navigate('/graph-chat');
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
                {progress < 100 ? `processing... ${progress}%` : eta ? `completing... eta ${eta}s` : 'finishing...'}
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
