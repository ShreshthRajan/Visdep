/**
 * Authentication Context
 *
 * Manages user authentication state across the app
 * Handles GitHub OAuth flow via backend
 */

import React, { createContext, useState, useEffect, useContext } from 'react';
import { supabase } from '../lib/supabase';

const AuthContext = createContext({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  githubToken: null,
  login: () => {},
  logout: () => {},
  setUserData: () => {}
});

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [githubToken, setGithubToken] = useState(null);

  // Check for existing session on mount
  useEffect(() => {
    const checkAuth = async () => {
      try {
        // Check localStorage for user data
        const storedUser = localStorage.getItem('visdep_user');
        const storedToken = localStorage.getItem('visdep_github_token');

        if (storedUser && storedToken) {
          const userData = JSON.parse(storedUser);
          setUser(userData);
          setGithubToken(storedToken);
          setIsAuthenticated(true);
          console.log('✅ Restored user session:', userData.username);
        }
      } catch (error) {
        console.error('Error checking auth:', error);
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  const login = () => {
    // Redirect to backend OAuth endpoint
    const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000';
    window.location.href = `${apiUrl}/api/auth/github`;
  };

  const setUserData = (userData, token) => {
    setUser(userData);
    setGithubToken(token);
    setIsAuthenticated(true);

    // Persist to localStorage
    localStorage.setItem('visdep_user', JSON.stringify(userData));
    localStorage.setItem('visdep_github_token', token);

    console.log('✅ User authenticated:', userData.username);
  };

  const logout = async () => {
    // Clear local state
    setUser(null);
    setGithubToken(null);
    setIsAuthenticated(false);

    // Clear localStorage
    localStorage.removeItem('visdep_user');
    localStorage.removeItem('visdep_github_token');

    console.log('✅ User logged out');

    // Redirect to landing
    window.location.href = '/';
  };

  const value = {
    user,
    isAuthenticated,
    isLoading,
    githubToken,
    login,
    logout,
    setUserData
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};

export default AuthContext;
