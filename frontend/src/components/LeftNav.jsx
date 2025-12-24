import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

/**
 * Professional Access Rail - Cockpit Design
 *
 * Three Zones:
 * - Top: Home (landing page)
 * - Center: The Library (repos) + The Timeline (chats)
 * - Bottom: User Profile (circular PFP)
 *
 * Design Philosophy:
 * - Bare icons (no button backgrounds)
 * - Subtle states (gray → cyan)
 * - Active glow (mechanical indicator)
 * - Generous spacing (gap-8)
 */
const LeftNav = ({ activeView = null, onHistoryClick, onChatsClick }) => {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  return (
    <div
      className="w-16 flex-none flex flex-col items-center py-6 relative"
      style={{
        backgroundColor: '#080808',
        backgroundImage: 'linear-gradient(to bottom, transparent, transparent, rgba(0,0,0,0.1))',
        backdropFilter: 'blur(24px)',
        borderRight: '1px solid rgba(255, 255, 255, 0.05)'
      }}
    >
      {/* Top: Home */}
      <div className="relative">
        <button
          onClick={() => navigate('/')}
          className="relative flex items-center justify-center transition-all duration-200 group"
          title="Home"
          style={{
            width: '40px',
            height: '40px'
          }}
        >
          {/* Cyan strip for active state (2px wide, far-left edge) */}
          {'home' === activeView && (
            <div
              className="absolute"
              style={{
                left: '-24px',
                top: '50%',
                transform: 'translateY(-50%)',
                width: '2px',
                height: '24px',
                backgroundColor: '#22d3ee'
              }}
            />
          )}

          {/* Active state glow halo */}
          {'home' === activeView && (
            <div
              className="absolute inset-0 rounded-full"
              style={{
                backgroundColor: 'rgba(34, 211, 238, 0.1)',
                filter: 'blur(12px)'
              }}
            />
          )}

          <HomeIcon
            className="w-5 h-5 relative z-10 transition-all duration-200"
            style={{
              color: 'home' === activeView ? '#22d3ee' : '#71717a',
              filter: 'home' === activeView ? 'drop-shadow(0 0 8px rgba(34, 211, 238, 0.4))' : 'none',
              transform: 'translateX(0)'
            }}
            isActive={'home' === activeView}
          />
        </button>
      </div>

      {/* Center: Library + Timeline (grouped with generous spacing) */}
      <div className="flex flex-col gap-8 mt-8">
        {/* The Library (Grid - Repos) */}
        <div className="relative">
          <button
            onClick={onHistoryClick}
            className="relative flex items-center justify-center transition-all duration-200 group"
            title="The Library"
            style={{
              width: '40px',
              height: '40px'
            }}
          >
            {'history' === activeView && (
              <div
                className="absolute"
                style={{
                  left: '-24px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  width: '2px',
                  height: '24px',
                  backgroundColor: '#22d3ee'
                }}
              />
            )}

            {'history' === activeView && (
              <div
                className="absolute inset-0 rounded-full"
                style={{
                  backgroundColor: 'rgba(34, 211, 238, 0.1)',
                  filter: 'blur(12px)'
                }}
              />
            )}

            <GridIcon
              className="w-5 h-5 relative z-10 transition-all duration-200 group-hover:translate-x-0.5"
              style={{
                color: 'history' === activeView ? '#22d3ee' : '#71717a',
                filter: 'history' === activeView ? 'drop-shadow(0 0 8px rgba(34, 211, 238, 0.4))' : 'none'
              }}
              isActive={'history' === activeView}
            />
          </button>
        </div>

        {/* The Timeline (Clock - Chats) */}
        <div className="relative">
          <button
            onClick={onChatsClick}
            className="relative flex items-center justify-center transition-all duration-200 group"
            title="The Timeline"
            style={{
              width: '40px',
              height: '40px'
            }}
          >
            {'chats' === activeView && (
              <div
                className="absolute"
                style={{
                  left: '-24px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  width: '2px',
                  height: '24px',
                  backgroundColor: '#22d3ee'
                }}
              />
            )}

            {'chats' === activeView && (
              <div
                className="absolute inset-0 rounded-full"
                style={{
                  backgroundColor: 'rgba(34, 211, 238, 0.1)',
                  filter: 'blur(12px)'
                }}
              />
            )}

            <ClockIcon
              className="w-5 h-5 relative z-10 transition-all duration-200 group-hover:translate-x-0.5"
              style={{
                color: 'chats' === activeView ? '#22d3ee' : '#71717a',
                filter: 'chats' === activeView ? 'drop-shadow(0 0 8px rgba(34, 211, 238, 0.4))' : 'none'
              }}
              isActive={'chats' === activeView}
            />
          </button>
        </div>
      </div>

      {/* Bottom: User Profile (circular PFP) */}
      {user && (
        <div className="mt-auto flex flex-col items-center">
          {/* Anchor divider */}
          <div
            className="mb-4"
            style={{
              width: '32px',
              height: '1px',
              backgroundColor: 'rgba(255, 255, 255, 0.1)'
            }}
          />

          <button
            onClick={() => {
              if (window.confirm('Sign out?')) {
                logout();
              }
            }}
            className="rounded-full overflow-hidden transition-all duration-200 profile-button"
            style={{
              width: '40px',
              height: '40px',
              opacity: 0.7,
              filter: 'grayscale(100%)'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.opacity = '1';
              e.currentTarget.style.filter = 'grayscale(0%)';
              e.currentTarget.style.boxShadow = '0 0 0 2px #080808, 0 0 0 4px rgba(34, 211, 238, 0.5)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.opacity = '0.7';
              e.currentTarget.style.filter = 'grayscale(100%)';
              e.currentTarget.style.boxShadow = '0 0 0 2px #080808, 0 0 0 4px #27272a';
            }}
            title={`Signed in as ${user.username}`}
          >
            <img
              src={user.avatar_url}
              alt={user.username}
              className="w-full h-full object-cover"
              style={{
                boxShadow: '0 0 0 2px #080808, 0 0 0 4px #27272a'
              }}
            />
          </button>
        </div>
      )}

      {/* CSS for hover state on icons */}
      <style>{`
        .group:hover .w-5 {
          color: #d4d4d8 !important;
        }
      `}</style>
    </div>
  );
};

// SVG Icons (Sharp, high-contrast)
const HomeIcon = ({ className, style, isActive }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
  </svg>
);

const GridIcon = ({ className, style, isActive }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zM14 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
  </svg>
);

const ClockIcon = ({ className, style, isActive }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

export default LeftNav;
