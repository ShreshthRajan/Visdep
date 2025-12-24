/**
 * Chat History Panel - Shows chat sessions for current repo
 *
 * Opened from Layers button in LeftNav
 * Lists all chat sessions for the active repo
 * Click to load chat + restore graph state
 */

import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import API from '../api';

const ChatHistoryPanel = ({ isOpen, onClose, currentRepo, onLoadSession, onNewChat }) => {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(false);
  const { user } = useAuth();

  useEffect(() => {
    if (isOpen && user && currentRepo) {
      loadSessions();
    }
  }, [isOpen, user, currentRepo]);

  const loadSessions = async () => {
    try {
      setLoading(true);
      const response = await API.get(`/api/user/${user.id}/repo/${currentRepo.id}/sessions`);
      setSessions(response.data);
      console.log(`✅ Loaded ${response.data.length} chats for ${currentRepo.repo_name}`);
    } catch (error) {
      console.error('Error loading sessions:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSessionClick = (session) => {
    onLoadSession(session);
    onClose();
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

      {/* Panel (right side, narrower) */}
      <div
        className="fixed right-96 top-0 bottom-0 w-72 z-50 animate-slide-in-right"
        style={{
          backgroundColor: 'rgba(5, 5, 5, 0.6)',
          backdropFilter: 'blur(48px)',
          borderLeft: '1px solid #27272a'
        }}
      >
        {/* Header */}
        <div
          className="px-4 py-3 flex items-center justify-between"
          style={{
            borderBottom: '1px solid rgba(255, 255, 255, 0.05)'
          }}
        >
          <div>
            <h2
              style={{
                fontSize: '11px',
                fontWeight: 600,
                color: '#e5e5e7',
                fontFamily: "'JetBrains Mono', monospace",
                textTransform: 'uppercase',
                letterSpacing: '0.1em'
              }}
            >
              Chat History
            </h2>
            {currentRepo && (
              <p
                style={{
                  fontSize: '9px',
                  color: '#52525b',
                  fontFamily: "'JetBrains Mono', monospace",
                  marginTop: '2px'
                }}
              >
                {currentRepo.repo_name}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            style={{
              color: '#52525b',
              fontSize: '18px',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer'
            }}
            onMouseEnter={(e) => e.target.style.color = '#22d3ee'}
            onMouseLeave={(e) => e.target.style.color = '#52525b'}
          >
            ×
          </button>
        </div>

        {/* Chat List */}
        <div className="overflow-y-auto px-4 py-4" style={{ height: 'calc(100% - 120px)' }}>
          {loading ? (
            <div className="flex justify-center py-8">
              <div
                className="animate-spin rounded-full h-6 w-6 border-b-2"
                style={{ borderColor: '#22d3ee' }}
              />
            </div>
          ) : sessions.length === 0 ? (
            <p
              style={{
                fontSize: '10px',
                color: '#52525b',
                fontFamily: "'JetBrains Mono', monospace",
                textAlign: 'center',
                paddingTop: '32px'
              }}
            >
              // No chats yet
            </p>
          ) : (
            sessions.map(session => (
              <div
                key={session.id}
                onClick={() => handleSessionClick(session)}
                className="mb-2 px-3 py-2 rounded cursor-pointer transition-all hover:bg-white/5"
                style={{
                  border: '1px solid rgba(63, 63, 70, 0.3)'
                }}
              >
                <p
                  style={{
                    fontSize: '11px',
                    color: '#e5e5e7',
                    fontFamily: "'JetBrains Mono', monospace",
                    marginBottom: '4px'
                  }}
                >
                  {session.title || 'Untitled'}
                </p>
                <div className="flex items-center justify-between">
                  <span
                    style={{
                      fontSize: '9px',
                      color: '#52525b',
                      fontFamily: "'JetBrains Mono', monospace"
                    }}
                  >
                    {session.message_count} messages
                  </span>
                  <span
                    style={{
                      fontSize: '9px',
                      color: '#3f3f46',
                      fontFamily: "'JetBrains Mono', monospace"
                    }}
                  >
                    {new Date(session.updated_at).toRelativeTime()}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* New Chat Button */}
        <div
          className="px-4 py-3"
          style={{
            borderTop: '1px solid rgba(255, 255, 255, 0.05)'
          }}
        >
          <button
            onClick={() => {
              onNewChat();
              onClose();
            }}
            className="w-full px-3 py-2 rounded transition-all"
            style={{
              backgroundColor: 'transparent',
              border: '1px solid rgba(63, 63, 70, 0.6)',
              color: '#71717a',
              fontSize: '10px',
              fontFamily: "'JetBrains Mono', monospace",
              letterSpacing: '0.02em'
            }}
            onMouseEnter={(e) => {
              e.target.style.borderColor = '#22d3ee';
              e.target.style.color = '#22d3ee';
            }}
            onMouseLeave={(e) => {
              e.target.style.borderColor = 'rgba(63, 63, 70, 0.6)';
              e.target.style.color = '#71717a';
            }}
          >
            + new chat
          </button>
        </div>
      </div>

      <style>{`
        @keyframes slide-in-right {
          from {
            transform: translateX(100%);
            opacity: 0;
          }
          to {
            transform: translateX(0);
            opacity: 1;
          }
        }
        .animate-slide-in-right {
          animation: slide-in-right 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }
      `}</style>
    </>
  );
};

// Helper for relative time (same as HistoryPanel)
Date.prototype.toRelativeTime = function() {
  const seconds = Math.floor((new Date() - this) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 2592000) return `${Math.floor(seconds / 86400)}d ago`;
  return `${Math.floor(seconds / 2592000)}mo ago`;
};

export default ChatHistoryPanel;
