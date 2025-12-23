/**
 * OAuth Callback Handler
 *
 * Receives OAuth code from GitHub
 * Exchanges for user data via backend
 * Redirects to graph-chat
 */

import React, { useEffect, useState, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import API from '../api';

const AuthCallback = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { setUserData } = useAuth();
  const [error, setError] = useState(null);
  const processedRef = useRef(false);  // Prevent double-processing in StrictMode

  useEffect(() => {
    // Prevent multiple executions (React StrictMode double-mounts)
    if (processedRef.current) {
      return;
    }

    const handleCallback = async () => {
      try {
        const code = searchParams.get('code');

        if (!code) {
          setError('No authorization code received');
          return;
        }

        // Mark as processed immediately
        processedRef.current = true;

        console.log('🔐 Processing OAuth callback...');

        // Exchange code for user data via backend
        const response = await API.get(`/api/auth/callback?code=${code}`);

        const { user, access_token } = response.data;

        // Store user data and GitHub token
        setUserData(user, access_token);

        console.log('✅ Authentication successful');

        // Redirect to landing (user is now logged in, can upload repos)
        navigate('/');

      } catch (err) {
        console.error('❌ OAuth callback error:', err);
        setError(err.response?.data?.detail || 'Authentication failed');

        // Redirect back to landing after 3s
        setTimeout(() => {
          navigate('/');
        }, 3000);
      }
    };

    handleCallback();
  }, [searchParams, navigate, setUserData]);

  return (
    <div
      className="flex items-center justify-center min-h-screen"
      style={{ backgroundColor: '#050505' }}
    >
      <div className="text-center">
        {error ? (
          <>
            <p style={{
              color: '#ef4444',
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '14px',
              marginBottom: '16px'
            }}>
              ❌ {error}
            </p>
            <p style={{
              color: '#71717a',
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '12px'
            }}>
              Redirecting to home...
            </p>
          </>
        ) : (
          <>
            <div
              className="animate-spin rounded-full h-12 w-12 border-b-2 mx-auto mb-4"
              style={{ borderColor: '#22d3ee' }}
            />
            <p style={{
              color: '#22d3ee',
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '12px'
            }}>
              Authenticating with GitHub...
            </p>
          </>
        )}
      </div>
    </div>
  );
};

export default AuthCallback;
