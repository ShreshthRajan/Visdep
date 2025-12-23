import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const Home = () => {
  const [repoUrl, setRepoUrl] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [mousePosition, setMousePosition] = useState({ x: 50, y: 50 });
  const fileInputRef = useRef(null);
  const navigate = useNavigate();
  const { user, login } = useAuth();

  const handleUpload = async () => {
    if (!repoUrl.trim()) return;

    sessionStorage.setItem('visdep_upload', JSON.stringify({
      repoUrl: repoUrl.trim(),
      subDirectory: ''
    }));

    navigate('/loading');
  };

  const handleDragEnter = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);

    const text = e.dataTransfer.getData('text');
    if (text.includes('github.com')) {
      setRepoUrl(text);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && repoUrl.trim()) {
      handleUpload();
    }
  };

  const handleMouseMove = (e) => {
    const x = (e.clientX / window.innerWidth) * 100;
    const y = (e.clientY / window.innerHeight) * 100;
    setMousePosition({ x, y });
  };

  return (
    <div
      className="relative w-screen h-screen overflow-hidden flex items-center justify-center"
      style={{
        backgroundColor: isDragging ? '#0a0a0f' : '#050505',
        transition: 'background-color 0.3s ease'
      }}
      onMouseMove={handleMouseMove}
    >
      {/* Technical Grid with Mouse Mask - More Visible */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: `
            linear-gradient(to right, rgba(255, 255, 255, 0.08) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(255, 255, 255, 0.08) 1px, transparent 1px)
          `,
          backgroundSize: '50px 50px',
          maskImage: `radial-gradient(circle 400px at ${mousePosition.x}% ${mousePosition.y}%, rgba(0,0,0,1) 0%, rgba(0,0,0,0) 100%)`,
          WebkitMaskImage: `radial-gradient(circle 400px at ${mousePosition.x}% ${mousePosition.y}%, rgba(0,0,0,1) 0%, rgba(0,0,0,0) 100%)`
        }}
      />

      {/* Ghost Rail - Top Right */}
      <div className="absolute top-6 right-6 z-50">
        <div
          className="px-4 py-2 rounded-full flex items-center gap-4"
          style={{
            backgroundColor: 'rgba(24, 24, 27, 0.5)',
            backdropFilter: 'blur(16px)',
            border: '1px solid rgba(39, 39, 42, 1)'
          }}
        >
          <a
            href="#"
            className="text-xs transition-colors"
            style={{
              color: '#71717a',
              fontFamily: "'Inter', sans-serif",
              textDecoration: 'none'
            }}
            onMouseEnter={(e) => e.target.style.color = '#22d3ee'}
            onMouseLeave={(e) => e.target.style.color = '#71717a'}
          >
            docs
          </a>
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs transition-colors"
            style={{
              color: '#71717a',
              fontFamily: "'Inter', sans-serif",
              textDecoration: 'none'
            }}
            onMouseEnter={(e) => e.target.style.color = '#22d3ee'}
            onMouseLeave={(e) => e.target.style.color = '#71717a'}
          >
            github
          </a>
        </div>
      </div>

      {/* Center Stack - The Machine */}
      <div className="relative z-10 flex flex-col items-center">
        {/* Headline - Inter Tight 900, Maximum Compression */}
        <h1
          className="mb-2"
          style={{
            fontFamily: "'Inter Tight', 'Inter', sans-serif",
            color: '#ffffff',
            fontSize: '104px',
            letterSpacing: '-0.08em',
            lineHeight: 0.85,
            fontWeight: 900,
            textAlign: 'center'
          }}
        >
          NAVIGATE THE
          <br />
          MACHINE.
        </h1>

        {/* Technical Status - JetBrains Mono */}
        <div
          className="text-xs mb-24"
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            color: '#71717a',
            letterSpacing: '0.05em',
            fontWeight: 500
          }}
        >
          [ STATUS: READY_FOR_INGESTION ]
        </div>

        {/* The Aperture - Drop Zone */}
        <div
          className="relative mb-10"
          style={{ width: '520px' }}
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
        >
          <div
            className="rounded-lg transition-all duration-300 cursor-pointer relative"
            style={{
              padding: '70px 50px',
              backgroundColor: 'transparent',
              border: isDragging
                ? '1px dashed rgba(34, 211, 238, 0.95)'
                : '1px dashed rgba(39, 39, 42, 1)',
              boxShadow: isDragging
                ? '0 0 25px rgba(34, 211, 238, 0.3), inset 0 0 80px rgba(34, 211, 238, 0.05)'
                : 'inset 0 0 100px rgba(34, 211, 238, 0.02)',
              filter: isDragging ? 'blur(0px)' : 'none'
            }}
          >
            {/* Radial Gradient Glow - Deep Well */}
            <div
              className="absolute inset-0 rounded-lg pointer-events-none"
              style={{
                background: 'radial-gradient(circle at center, rgba(34, 211, 238, 0.05) 0%, rgba(0, 0, 0, 0.95) 70%)',
                opacity: isDragging ? 1 : 0.4,
                transition: 'opacity 0.3s',
                animation: 'pulse 3s ease-in-out infinite'
              }}
            />

            {/* Technical Crosshair */}
            <div className="flex justify-center mb-12 relative">
              <svg
                width="56"
                height="56"
                viewBox="0 0 24 24"
                fill="none"
                stroke={isDragging ? '#22d3ee' : '#27272a'}
                strokeWidth="0.8"
                strokeLinecap="round"
                style={{
                  transition: 'stroke 0.3s, animation-play-state 0.3s',
                  animation: isDragging ? 'none' : 'spin 20s linear infinite',
                  animationPlayState: isDragging ? 'paused' : 'running',
                  filter: isDragging ? 'drop-shadow(0 0 8px rgba(34, 211, 238, 0.6))' : 'none'
                }}
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="1" x2="12" y2="5" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="1" y1="12" x2="5" y2="12" />
                <line x1="19" y1="12" x2="23" y2="12" />
                <circle cx="12" cy="12" r="2" fill={isDragging ? '#22d3ee' : '#27272a'} />
              </svg>
            </div>

            {/* Input - Borderless, Minimal */}
            <input
              ref={fileInputRef}
              type="text"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="https://github.com/org/repository"
              className="w-full px-0 py-2 text-center text-sm focus:outline-none transition-all bg-transparent"
              style={{
                color: '#e5e5e7',
                border: 'none',
                borderBottom: '1px solid rgba(39, 39, 42, 0.8)',
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '13px',
                letterSpacing: '-0.01em'
              }}
              onFocus={(e) => {
                e.target.style.borderBottomColor = '#22d3ee';
                e.target.style.color = '#ffffff';
              }}
              onBlur={(e) => {
                e.target.style.borderBottomColor = 'rgba(39, 39, 42, 0.8)';
                e.target.style.color = '#e5e5e7';
              }}
            />

            {/* Technical Prompt */}
            <div className="text-center mt-10 mb-8">
              <p
                className="text-xs"
                style={{
                  color: isDragging ? '#22d3ee' : '#52525b',
                  fontFamily: "'JetBrains Mono', monospace",
                  transition: 'color 0.3s',
                  letterSpacing: '0.02em'
                }}
              >
                {isDragging ? '// release to ingest' : '// click to upload or drop repository'}
              </p>
            </div>

            {/* Ghost Button - Transparent */}
            <button
              onClick={handleUpload}
              disabled={!repoUrl.trim()}
              className="w-full py-3.5 rounded transition-all text-xs disabled:opacity-15 disabled:cursor-not-allowed"
              style={{
                backgroundColor: 'transparent',
                color: repoUrl.trim() ? '#e5e5e7' : '#27272a',
                border: repoUrl.trim() ? '1px solid rgba(39, 39, 42, 1)' : '1px solid rgba(39, 39, 42, 0.5)',
                fontFamily: "'JetBrains Mono', monospace",
                fontWeight: 500,
                letterSpacing: '0.05em',
                textTransform: 'uppercase'
              }}
              onMouseEnter={(e) => {
                if (repoUrl.trim()) {
                  e.target.style.borderColor = '#22d3ee';
                  e.target.style.color = '#ffffff';
                  e.target.style.boxShadow = '0 0 15px rgba(34, 211, 238, 0.2)';
                }
              }}
              onMouseLeave={(e) => {
                if (repoUrl.trim()) {
                  e.target.style.borderColor = 'rgba(39, 39, 42, 1)';
                  e.target.style.color = '#e5e5e7';
                  e.target.style.boxShadow = 'none';
                }
              }}
            >
              ingest repository
            </button>
          </div>
        </div>

        {/* GitHub Auth Button - Shows login state */}
        {user ? (
          // Logged in - show user info
          <div
            className="px-5 py-2.5 rounded text-xs font-medium flex items-center gap-2 mt-6"
            style={{
              backgroundColor: 'transparent',
              border: '1px solid rgba(39, 39, 42, 0.8)',
              color: '#71717a',
              fontFamily: "'JetBrains Mono', monospace",
              letterSpacing: '0.02em'
            }}
          >
            <img
              src={user.avatar_url}
              alt={user.username}
              className="w-4 h-4 rounded-full"
            />
            <span>signed in as {user.username}</span>
          </div>
        ) : (
          // Not logged in - show connect button
          <button
            onClick={login}
            className="px-5 py-2.5 rounded text-xs font-medium transition-all flex items-center gap-2 mt-6"
            style={{
              backgroundColor: 'transparent',
              border: '1px solid rgba(39, 39, 42, 0.8)',
              color: '#52525b',
              fontFamily: "'JetBrains Mono', monospace",
              letterSpacing: '0.02em'
            }}
            onMouseEnter={(e) => {
              e.target.style.borderColor = '#22d3ee';
              e.target.style.color = '#22d3ee';
            }}
            onMouseLeave={(e) => {
              e.target.style.borderColor = 'rgba(39, 39, 42, 0.8)';
              e.target.style.color = '#52525b';
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" opacity="0.6">
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
            </svg>
            connect github
          </button>
        )}

        {/* Footer - Languages */}
        <div className="text-center mt-24">
          <p
            className="text-xs"
            style={{
              color: '#27272a',
              fontFamily: "'JetBrains Mono', monospace",
              letterSpacing: '0.05em'
            }}
          >
            py · js · ts · java · go · cpp · rust
          </p>
        </div>
      </div>

      {/* Animations */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }

        @keyframes pulse {
          0%, 100% {
            opacity: 0.4;
          }
          50% {
            opacity: 0.7;
          }
        }
      `}</style>
    </div>
  );
};

export default Home;
