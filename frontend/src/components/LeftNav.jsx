import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

/**
 * Micro-UI Access Rail - HUD Design
 *
 * Ultra-narrow, high-density navigation spine
 * Design: Fighter jet cockpit / Cursor-style precision
 *
 * Active state: 2px cyan dot (no boxes, no blooms)
 * Icons: Bare SVG glyphs floating in space
 * Profile: Tiny 24px circle
 */
const LeftNav = ({ activeView = null, onHistoryClick, onChatsClick }) => {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  return (
    <div
      className="w-14 flex-none flex flex-col items-center py-8 relative"
      style={{
        backgroundColor: 'rgba(0, 0, 0, 0.2)',
        backdropFilter: 'blur(48px) saturate(120%)',
        borderRight: '1px solid rgba(255, 255, 255, 0.05)'
      }}
    >
      {/* Top: Home */}
      <div className="relative">
        <button
          onClick={() => navigate('/')}
          className="relative transition-all duration-200 group"
          title="Home"
          style={{
            background: 'none',
            border: 'none',
            padding: 0,
            cursor: 'pointer'
          }}
        >
          {/* Active indicator: 2px cyan dot */}
          {'home' === activeView && (
            <div
              className="absolute"
              style={{
                left: '-16px',
                top: '50%',
                transform: 'translateY(-50%)',
                width: '2px',
                height: '2px',
                backgroundColor: '#22d3ee',
                borderRadius: '50%',
                boxShadow: '0 0 4px rgba(34, 211, 238, 0.8)'
              }}
            />
          )}

          <HomeIcon
            className="w-5 h-5 transition-all duration-200"
            style={{
              color: 'home' === activeView ? '#22d3ee' : '#52525b',
              filter: 'home' === activeView ? 'drop-shadow(0 0 6px rgba(34, 211, 238, 0.5))' : 'none'
            }}
          />
        </button>
      </div>

      {/* Center: Library + Timeline */}
      <div className="flex flex-col gap-8 mt-12">
        {/* The Library (Grid - Repos) */}
        <div className="relative">
          <button
            onClick={onHistoryClick}
            className="relative transition-all duration-200 group"
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
                  left: '-16px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  width: '2px',
                  height: '2px',
                  backgroundColor: '#22d3ee',
                  borderRadius: '50%',
                  boxShadow: '0 0 4px rgba(34, 211, 238, 0.8)'
                }}
              />
            )}

            <GridIcon
              className="w-5 h-5 transition-all duration-200 group-hover:text-zinc-400"
              style={{
                color: 'history' === activeView ? '#22d3ee' : '#52525b',
                filter: 'history' === activeView ? 'drop-shadow(0 0 6px rgba(34, 211, 238, 0.5))' : 'none'
              }}
            />
          </button>
        </div>

        {/* The Timeline (Clock - Chats) */}
        <div className="relative">
          <button
            onClick={onChatsClick}
            className="relative transition-all duration-200 group"
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
                  left: '-16px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  width: '2px',
                  height: '2px',
                  backgroundColor: '#22d3ee',
                  borderRadius: '50%',
                  boxShadow: '0 0 4px rgba(34, 211, 238, 0.8)'
                }}
              />
            )}

            <ClockIcon
              className="w-5 h-5 transition-all duration-200 group-hover:text-zinc-400"
              style={{
                color: 'chats' === activeView ? '#22d3ee' : '#52525b',
                filter: 'chats' === activeView ? 'drop-shadow(0 0 6px rgba(34, 211, 238, 0.5))' : 'none'
              }}
            />
          </button>
        </div>
      </div>

      {/* Bottom: User Profile (tiny 24px circle) */}
      {user && (
        <div className="mt-auto flex flex-col items-center">
          {/* Micro divider */}
          <div
            className="mb-3"
            style={{
              width: '20px',
              height: '1px',
              backgroundColor: 'rgba(255, 255, 255, 0.08)'
            }}
          />

          <button
            onClick={() => {
              if (window.confirm('Sign out?')) {
                logout();
              }
            }}
            className="rounded-full overflow-hidden transition-all duration-200"
            style={{
              width: '24px',
              height: '24px',
              opacity: 0.5,
              filter: 'grayscale(100%)',
              border: 'none',
              padding: 0,
              cursor: 'pointer'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.opacity = '1';
              e.currentTarget.style.filter = 'grayscale(0%)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.opacity = '0.5';
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

// SVG Icons (Sharp, minimal stroke)
const HomeIcon = ({ className, style }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
  </svg>
);

const GridIcon = ({ className, style }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zM14 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
  </svg>
);

const ClockIcon = ({ className, style }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

export default LeftNav;
