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

  // Effect 3: Upload and progress visualization (runs ONCE on mount)
  useEffect(() => {
    if (!repoUrl) return;  // Guard clause - already redirected by Effect 1

    // Mark upload as started - prevents redirect during navigation
    uploadStartedRef.current = true;

    const uploadRepo = async () => {
      const repoName = repoUrl.split('/').pop() || 'repository';

      const steps = [
        { progress: 5, log: `[LOAD]: Indexing repository...`, delay: 300 },
        { progress: 10, log: `-> Found ${repoName}`, delay: 500, addNode: { id: 'root', label: repoName, x: 0, y: 0 } },
        { progress: 15, log: '[GIT]: Cloning codebase...', delay: 700 },
        { progress: 22, log: '-> Found 127 python files.', delay: 600, addNode: { id: 'src', label: 'src/', x: -100, y: 50 }, addEdge: { from: 'root', to: 'src' } },
        { progress: 30, log: '[AST]: Building tree for /src/auth...', delay: 800, addNode: { id: 'auth', label: 'auth.py', x: -150, y: 120 }, addEdge: { from: 'src', to: 'auth' } },
        { progress: 38, log: '[SUCCESS]: Node #127 linked.', delay: 700, addNode: { id: 'models', label: 'models.py', x: 100, y: 50 }, addEdge: { from: 'root', to: 'models' } },
        { progress: 45, log: '[AST]: Building tree for /src/api...', delay: 900, addNode: { id: 'api', label: 'api.py', x: 0, y: 120 }, addEdge: { from: 'src', to: 'api' } },
        { progress: 52, log: '[SUCCESS]: Node #284 linked.', delay: 600, addNode: { id: 'utils', label: 'utils.py', x: 150, y: 120 }, addEdge: { from: 'models', to: 'utils' } },
        { progress: 60, log: '[CHUNK]: Processing method-level chunks...', delay: 1000 },
        { progress: 68, log: '[EMBED]: OpenAI embeddings (batch 1/3)...', delay: 1100, addNode: { id: 'sessions', label: 'sessions', x: -100, y: 190 }, addEdge: { from: 'auth', to: 'sessions' } },
        { progress: 75, log: '[EMBED]: OpenAI embeddings (batch 2/3)...', delay: 900, addNode: { id: 'hooks', label: 'hooks', x: 100, y: 190 }, addEdge: { from: 'api', to: 'hooks' } },
        { progress: 82, log: '[FAISS]: Building vector index...', delay: 800 },
        { progress: 88, log: '[SUCCESS]: Node #842 linked.', delay: 700 },
        { progress: 92, log: '[GRAPH]: NetworkX force-atlas2...', delay: 600 },
        { progress: 95, log: '[HYBRID]: Initializing retriever...', delay: 500 },
        { progress: 97, log: '[CANVAS]: Preparing visualization...', delay: 800 },
        { progress: 98, log: '[LAYOUT]: Computing node positions...', delay: 700 },
        { progress: 99, log: '[RENDER]: Organizing clusters...', delay: 900 },
        { progress: 100, log: '[READY]: AST engine initialized.', delay: 600 }
      ];

      try {
        // Start real upload in background
        // Phase 2: Include user_id and github_token for private repos
        const uploadPayload = {
          repo_url: repoUrl,
          sub_directory: subDirectory
        };

        if (user && user.id) {
          uploadPayload.user_id = user.id;
        }

        if (githubToken) {
          uploadPayload.github_token = githubToken;
        }

        const uploadPromise = API.post('/api/upload_repo', uploadPayload);

        // Visual progress feedback
        for (const stepData of steps) {
          await new Promise(resolve => setTimeout(resolve, stepData.delay));

          setProgress(stepData.progress);
          setLogs(prev => [...prev, stepData.log]);

          // Add ghost nodes to graph
          if (stepData.addNode && networkInstance.current) {
            const nodesDataSet = networkInstance.current.body.data.nodes;
            nodesDataSet.add(stepData.addNode);
          }

          if (stepData.addEdge && networkInstance.current) {
            const edgesDataSet = networkInstance.current.body.data.edges;
            edgesDataSet.add({ id: `edge_${stepData.addEdge.from}_${stepData.addEdge.to}`, ...stepData.addEdge });
          }
        }

        // Show backend processing message (large repos take 2-5 min)
        setLogs(prev => [...prev, '[BACKEND]: Processing on server...']);
        setLogs(prev => [...prev, '[BACKEND]: Large repos may take 2-5 minutes...']);
        await new Promise(resolve => setTimeout(resolve, 500));

        // Wait for real upload to complete
        await uploadPromise;

        // Final success log
        setLogs(prev => [...prev, '[COMPLETE]: Repository ready']);

        // Phase 3: Fetch the repo that was just uploaded (for currentRepo state)
        if (user) {
          try {
            const userReposResponse = await API.get(`/api/user/${user.id}/repos`);
            const repos = userReposResponse.data;

            if (repos && repos.length > 0) {
              // Most recent repo (just uploaded)
              const justUploaded = repos[0];
              sessionStorage.setItem('visdep_current_repo', JSON.stringify(justUploaded));
              console.log('✅ Stored current repo for GraphChat');
            }
          } catch (err) {
            console.error('⚠️ Could not fetch uploaded repo:', err);
          }
        }

        // Small delay for final log
        await new Promise(resolve => setTimeout(resolve, 400));

        // White-out flash transition (camera shutter)
        setShowFlash(true);

        // Wait for flash animation
        await new Promise(resolve => setTimeout(resolve, 500));

        // Navigate to graph
        navigate('/graph-chat');

      } catch (error) {
        console.error('Upload error:', error);
        setLogs(prev => [...prev, `[ERROR]: ${error.response?.data?.detail || error.message || 'Upload failed'}`]);
        setLogs(prev => [...prev, `[ERROR]: Upload failed. Check backend is running.`]);

        // Stay on loading page showing error (don't redirect)
        // User can manually navigate back
      }
    };

    uploadRepo();
  }, [repoUrl, subDirectory, navigate]);

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
                {progress < 100 ? `building... ${progress}%` : 'finalizing...'}
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
