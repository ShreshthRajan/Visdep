/**
 * History Panel - Shows user's repos
 *
 * Slides from left when History button clicked
 * Lists all user's repositories
 * Click to load repo
 */

import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import API from '../api';

const HistoryPanel = ({ isOpen, onClose, onLoadRepo }) => {
  const [repos, setRepos] = useState([]);
  const [loading, setLoading] = useState(false);
  const { user } = useAuth();

  useEffect(() => {
    if (isOpen && user) {
      loadUserRepos();
    }
  }, [isOpen, user]);

  const loadUserRepos = async () => {
    try {
      setLoading(true);
      const response = await API.get(`/api/user/${user.id}/repos`);
      setRepos(response.data);
      console.log(`✅ Loaded ${response.data.length} repos for user`);
    } catch (error) {
      console.error('Error loading repos:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRepoClick = async (repo) => {
    try {
      // Activate this repo as the current one
      await API.post(`/api/repos/${repo.local_repo_id}/activate`);

      console.log(`✅ Activated repo: ${repo.repo_name}`);

      // Notify parent to load this repo
      onLoadRepo(repo);

      // Close panel
      onClose();
    } catch (error) {
      console.error('Error loading repo:', error);
    }
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 z-40 bg-black/50"
        onClick={onClose}
        style={{ backdropFilter: 'blur(4px)' }}
      />

      {/* Panel */}
      <div
        className="fixed left-16 top-0 bottom-0 w-80 z-50 animate-slide-in-left"
        style={{
          backgroundColor: 'rgba(9, 9, 11, 0.95)',
          backdropFilter: 'blur(48px)',
          borderRight: '1px solid rgba(255, 255, 255, 0.1)'
        }}
      >
        {/* Header */}
        <div
          className="px-6 py-4 flex items-center justify-between"
          style={{
            borderBottom: '1px solid rgba(255, 255, 255, 0.05)'
          }}
        >
          <h2
            style={{
              fontSize: '12px',
              fontWeight: 600,
              color: '#e5e5e7',
              fontFamily: "'JetBrains Mono', monospace",
              textTransform: 'uppercase',
              letterSpacing: '0.1em'
            }}
          >
            Your Repositories
          </h2>
          <button
            onClick={onClose}
            style={{
              color: '#52525b',
              fontSize: '20px',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              transition: 'color 0.2s'
            }}
            onMouseEnter={(e) => e.target.style.color = '#22d3ee'}
            onMouseLeave={(e) => e.target.style.color = '#52525b'}
          >
            ×
          </button>
        </div>

        {/* Repo List */}
        <div className="overflow-y-auto" style={{ height: 'calc(100% - 60px)' }}>
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div
                className="animate-spin rounded-full h-8 w-8 border-b-2"
                style={{ borderColor: '#22d3ee' }}
              />
            </div>
          ) : repos.length === 0 ? (
            <div className="px-6 py-12 text-center">
              <p
                style={{
                  fontSize: '11px',
                  color: '#52525b',
                  fontFamily: "'JetBrains Mono', monospace"
                }}
              >
                // No repositories uploaded yet
              </p>
            </div>
          ) : (
            repos.map(repo => (
              <div
                key={repo.id}
                onClick={() => handleRepoClick(repo)}
                className="px-6 py-4 cursor-pointer transition-all hover:bg-white/5"
                style={{
                  borderBottom: '1px solid rgba(255, 255, 255, 0.03)'
                }}
              >
                <div className="flex items-start justify-between mb-1">
                  <span
                    style={{
                      fontSize: '12px',
                      color: '#e5e5e7',
                      fontFamily: "'JetBrains Mono', monospace",
                      fontWeight: 500
                    }}
                  >
                    {repo.repo_name.split('/')[1] || repo.repo_name}
                  </span>
                  {repo.is_private && (
                    <span
                      style={{
                        fontSize: '9px',
                        color: '#71717a',
                        fontFamily: "'JetBrains Mono', monospace",
                        backgroundColor: 'rgba(113, 113, 122, 0.2)',
                        padding: '2px 6px',
                        borderRadius: '3px'
                      }}
                    >
                      private
                    </span>
                  )}
                </div>
                <p
                  style={{
                    fontSize: '10px',
                    color: '#52525b',
                    fontFamily: "'JetBrains Mono', monospace"
                  }}
                >
                  {repo.repo_name.split('/')[0]}
                </p>
                <p
                  style={{
                    fontSize: '9px',
                    color: '#3f3f46',
                    fontFamily: "'JetBrains Mono', monospace",
                    marginTop: '4px'
                  }}
                >
                  {new Date(repo.last_accessed).toRelativeTime()}
                </p>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Slide animation */}
      <style>{`
        @keyframes slide-in-left {
          from {
            transform: translateX(-100%);
            opacity: 0;
          }
          to {
            transform: translateX(0);
            opacity: 1;
          }
        }
        .animate-slide-in-left {
          animation: slide-in-left 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }
      `}</style>
    </>
  );
};

// Helper for relative time display
Date.prototype.toRelativeTime = function() {
  const seconds = Math.floor((new Date() - this) / 1000);

  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 2592000) return `${Math.floor(seconds / 86400)}d ago`;
  return `${Math.floor(seconds / 2592000)}mo ago`;
};

export default HistoryPanel;
