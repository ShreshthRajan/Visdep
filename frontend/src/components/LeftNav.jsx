import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

/**
 * Ultra-Minimal Access Rail - Production Design
 *
 * Design Philosophy:
 * - Invisible until needed (almost-black inactive state)
 * - Micro-sized icons (14px, matches 10px text paradigm)
 * - Pure transparency (5% background, no border)
 * - Recedes completely (only active/hover states visible)
 *
 * Matches existing UI: 10px text, dark grays, minimal chrome
 */
const LeftNav = ({ activeView = null, onHistoryClick, onChatsClick }) => {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  return (
    <div
      className="w-14 flex-none flex flex-col items-center py-8 relative"
      style={{
        backgroundColor: '#0A0A0A',
        borderRight: '1px solid rgba(255, 255, 255, 0.1)'
      }}
    >
      {/* Top: Home */}
      <div className="relative">
        <button
          onClick={() => navigate('/')}
          className="relative transition-all duration-300 ease-out group"
          title="Home"
          style={{
            background: 'none',
            border: 'none',
            padding: 0,
            cursor: 'pointer'
          }}
        >
          {/* Active indicator: 2px x 24px vertical bar */}
          {'home' === activeView && (
            <div
              className="absolute"
              style={{
                left: '-1px',
                top: '50%',
                transform: 'translateY(-50%)',
                width: '2px',
                height: '24px',
                backgroundColor: '#22d3ee',
                filter: 'blur(4px)',
                boxShadow: '0 0 12px #22d3ee'
              }}
            />
          )}

          <HomeIcon
            className="w-3.5 h-3.5 transition-all duration-300 ease-out group-hover:scale-110"
            style={{
              color: 'home' === activeView ? '#22d3ee' : '#71717a',
              opacity: 'home' === activeView ? 1 : 0.6,
              filter: 'home' === activeView 
                ? 'drop-shadow(0 0 12px #22d3ee)' 
                : 'none'
            }}
            onMouseEnter={(e) => {
              if ('home' !== activeView) {
                e.currentTarget.style.color = '#ffffff';
                e.currentTarget.style.opacity = '1';
                e.currentTarget.style.filter = 'drop-shadow(0 0 8px rgba(255, 255, 255, 0.3))';
              }
            }}
            onMouseLeave={(e) => {
              if ('home' !== activeView) {
                e.currentTarget.style.color = '#71717a';
                e.currentTarget.style.opacity = '0.6';
                e.currentTarget.style.filter = 'none';
              }
            }}
          />
        </button>
      </div>

      {/* Center: Library + Timeline */}
      <div className="flex flex-col gap-8 mt-6">
        {/* The Library (Grid - Repos) */}
        <div className="relative">
          <button
            onClick={onHistoryClick}
            className="relative transition-all duration-300 ease-out group"
            title="The Library"
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: 'pointer'
            }}
          >
            {'history' === activeView && (
              <div
                className="absolute"
                style={{
                  left: '-1px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  width: '2px',
                  height: '24px',
                  backgroundColor: '#22d3ee',
                  filter: 'blur(4px)',
                  boxShadow: '0 0 12px #22d3ee'
                }}
              />
            )}

            <GridIcon
              className="w-3.5 h-3.5 transition-all duration-300 ease-out group-hover:scale-110"
              style={{
                color: 'history' === activeView ? '#22d3ee' : '#71717a',
                opacity: 'history' === activeView ? 1 : 0.6,
                filter: 'history' === activeView 
                  ? 'drop-shadow(0 0 12px #22d3ee)' 
                  : 'none'
              }}
              onMouseEnter={(e) => {
                if ('history' !== activeView) {
                  e.currentTarget.style.color = '#ffffff';
                  e.currentTarget.style.opacity = '1';
                  e.currentTarget.style.filter = 'drop-shadow(0 0 8px rgba(255, 255, 255, 0.3))';
                }
              }}
              onMouseLeave={(e) => {
                if ('history' !== activeView) {
                  e.currentTarget.style.color = '#71717a';
                  e.currentTarget.style.opacity = '0.6';
                  e.currentTarget.style.filter = 'none';
                }
              }}
            />
          </button>
        </div>

        {/* The Timeline (Clock - Chats) */}
        <div className="relative">
          <button
            onClick={onChatsClick}
            className="relative transition-all duration-300 ease-out group"
            title="The Timeline"
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: 'pointer'
            }}
          >
            {'chats' === activeView && (
              <div
                className="absolute"
                style={{
                  left: '-1px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  width: '2px',
                  height: '24px',
                  backgroundColor: '#22d3ee',
                  filter: 'blur(4px)',
                  boxShadow: '0 0 12px #22d3ee'
                }}
              />
            )}

            <ClockIcon
              className="w-3.5 h-3.5 transition-all duration-300 ease-out group-hover:scale-110"
              style={{
                color: 'chats' === activeView ? '#22d3ee' : '#71717a',
                opacity: 'chats' === activeView ? 1 : 0.6,
                filter: 'chats' === activeView 
                  ? 'drop-shadow(0 0 12px #22d3ee)' 
                  : 'none'
              }}
              onMouseEnter={(e) => {
                if ('chats' !== activeView) {
                  e.currentTarget.style.color = '#ffffff';
                  e.currentTarget.style.opacity = '1';
                  e.currentTarget.style.filter = 'drop-shadow(0 0 8px rgba(255, 255, 255, 0.3))';
                }
              }}
              onMouseLeave={(e) => {
                if ('chats' !== activeView) {
                  e.currentTarget.style.color = '#71717a';
                  e.currentTarget.style.opacity = '0.6';
                  e.currentTarget.style.filter = 'none';
                }
              }}
            />
          </button>
        </div>
      </div>

      {/* Bottom: User Profile (micro 16px circle) */}
      {user && (
        <div className="mt-auto flex flex-col items-center">
          {/* Divider: 20px above PFP */}
          <div
            className="mb-5"
            style={{
              width: '16px',
              height: '1px',
              backgroundColor: 'rgba(255, 255, 255, 0.05)'
            }}
          />

          <button
            onClick={() => {
              if (window.confirm('Sign out?')) {
                logout();
              }
            }}
            className="rounded-full overflow-hidden transition-all duration-300 ease-out"
            style={{
              width: '16px',
              height: '16px',
              filter: 'grayscale(100%)',
              border: 'none',
              padding: 0,
              cursor: 'pointer'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.filter = 'grayscale(0%)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.filter = 'grayscale(100%)';
            }}
            title={`Signed in as ${user.username}`}
          >
            <img
              src={user.avatar_url}
              alt={user.username}
              className="w-full h-full object-cover"
            />
          </button>
        </div>
      )}
    </div>
  );
};

// SVG Icons (Ultra-thin stroke for minimal aesthetic)
const HomeIcon = ({ className, style }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
  </svg>
);

const GridIcon = ({ className, style }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zM14 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
  </svg>
);

const ClockIcon = ({ className, style }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

export default LeftNav;
