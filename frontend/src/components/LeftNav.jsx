import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

/**
 * Minimalist Access Rail
 *
 * Three Zones:
 * - Top: Home (landing page)
 * - Center: The Library (repos) + The Timeline (chats)
 * - Bottom: User Profile (circular PFP)
 *
 * Active state: 2px cyan-400 vertical strip on far-left edge
 */
const LeftNav = ({ activeView = null, onHistoryClick, onChatsClick }) => {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  return (
    <div
      className="w-16 flex-none flex flex-col items-center py-6 relative"
      style={{
        backgroundColor: 'rgba(9, 9, 11, 0.7)',
        backdropFilter: 'blur(24px)',
        borderRight: '1px solid rgba(255, 255, 255, 0.1)'
      }}
    >
      {/* Top: Home */}
      <div className="relative">
        <button
          onClick={() => navigate('/')}
          className="w-10 h-10 flex items-center justify-center transition-all hover:bg-white/5 relative"
          title="Home"
        >
          {/* Cyan strip for active state (2px wide, far-left edge) */}
          {'home' === activeView && (
            <div
              className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-6"
              style={{
                backgroundColor: '#22d3ee',
                left: '0px',
                width: '2px'
              }}
            />
          )}
          <HomeIcon
            className="w-5 h-5"
            style={{
              color: 'home' === activeView ? '#22d3ee' : '#a1a1aa',
              transition: 'color 0.2s ease'
            }}
          />
        </button>
      </div>

      {/* Center: Library + Timeline (grouped) */}
      <div className="flex flex-col gap-3 mt-8">
        {/* The Library (Grid - Repos) */}
        <div className="relative">
          <button
            onClick={onHistoryClick}
            className="w-10 h-10 flex items-center justify-center transition-all hover:bg-white/5 relative"
            title="The Library"
          >
            {'history' === activeView && (
              <div
                className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-6"
                style={{
                  backgroundColor: '#22d3ee',
                  left: '0px',
                  width: '2px'
                }}
              />
            )}
            <GridIcon
              className="w-5 h-5"
              style={{
                color: 'history' === activeView ? '#22d3ee' : '#a1a1aa',
                transition: 'color 0.2s ease'
              }}
            />
          </button>
        </div>

        {/* The Timeline (Clock - Chats) */}
        <div className="relative">
          <button
            onClick={onChatsClick}
            className="w-10 h-10 flex items-center justify-center transition-all hover:bg-white/5 relative"
            title="The Timeline"
          >
            {'chats' === activeView && (
              <div
                className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-6"
                style={{
                  backgroundColor: '#22d3ee',
                  left: '0px',
                  width: '2px'
                }}
              />
            )}
            <ClockIcon
              className="w-5 h-5"
              style={{
                color: 'chats' === activeView ? '#22d3ee' : '#a1a1aa',
                transition: 'color 0.2s ease'
              }}
            />
          </button>
        </div>
      </div>

      {/* Bottom: User Profile (circular PFP) */}
      {user && (
        <div className="mt-auto">
          <button
            onClick={() => {
              if (window.confirm('Sign out?')) {
                logout();
              }
            }}
            className="w-10 h-10 rounded-full overflow-hidden transition-all"
            style={{
              border: '1px solid rgba(255, 255, 255, 0.1)',
              opacity: 0.7,
              filter: 'grayscale(100%)'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.opacity = '1';
              e.currentTarget.style.filter = 'grayscale(0%)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.opacity = '0.7';
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

// SVG Icons (Sharp, high-contrast)
const HomeIcon = ({ className, style }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
  </svg>
);

const GridIcon = ({ className, style }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zM14 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
  </svg>
);

const ClockIcon = ({ className, style }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

export default LeftNav;
