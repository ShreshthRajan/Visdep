import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const LeftNav = ({ activeView = 'map', onHistoryClick, onChatsClick }) => {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const navItems = [
    { id: 'home', icon: HomeIcon, label: 'Home', action: () => navigate('/') },
    { id: 'map', icon: MapIcon, label: 'Map', active: true },
    { id: 'history', icon: HistoryIcon, label: 'History', action: onHistoryClick },
    { id: 'chats', icon: LayersIcon, label: 'Chats', action: onChatsClick },  // Renamed: Layers → Chats
    { id: 'settings', icon: SettingsIcon, label: 'Settings' },
  ];

  return (
    <div
      className="w-16 flex-none flex flex-col items-center py-6 gap-6"
      style={{
        backgroundColor: 'rgba(9, 9, 11, 0.7)',
        backdropFilter: 'blur(24px)',
        borderRight: '1px solid rgba(255, 255, 255, 0.1)'
      }}
    >
      {navItems.map(item => (
        <button
          key={item.id}
          onClick={item.action}
          className="w-8 h-8 rounded-lg flex items-center justify-center transition-all hover:bg-white/10"
          style={{
            backgroundColor: item.id === activeView ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
            border: item.id === activeView ? '1px solid rgba(59, 130, 246, 0.3)' : '1px solid transparent'
          }}
          title={item.label}
        >
          <item.icon className="w-4 h-4" style={{ color: item.id === activeView ? '#3b82f6' : '#a1a1aa' }} />
        </button>
      ))}

      {/* User Avatar (Bottom) */}
      {user && (
        <div className="mt-auto">
          <button
            onClick={() => {
              if (window.confirm('Sign out?')) {
                logout();
              }
            }}
            className="w-8 h-8 rounded-full overflow-hidden transition-all"
            style={{
              border: '1px solid rgba(63, 63, 70, 0.5)',
              opacity: 0.8
            }}
            onMouseEnter={(e) => {
              e.target.style.opacity = '1';
              e.target.style.borderColor = '#22d3ee';
            }}
            onMouseLeave={(e) => {
              e.target.style.opacity = '0.8';
              e.target.style.borderColor = 'rgba(63, 63, 70, 0.5)';
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

// SVG Icons
const HomeIcon = ({ className, style }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
  </svg>
);

const MapIcon = ({ className, style }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
  </svg>
);

const HistoryIcon = ({ className, style }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const LayersIcon = ({ className, style }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zM14 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
  </svg>
);

const SettingsIcon = ({ className, style }) => (
  <svg className={className} style={style} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
);

export default LeftNav;
