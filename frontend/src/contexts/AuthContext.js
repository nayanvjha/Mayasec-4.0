import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

const AuthContext = createContext(null);

const TOKEN_KEY = 'mayasec_auth_token';

function getStoredToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

function setStoredToken(token) {
  try {
    if (!token) {
      localStorage.removeItem(TOKEN_KEY);
      return;
    }
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // no-op
  }
}

export function AuthProvider({ children, apiUrl }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(getStoredToken());
  const [loading, setLoading] = useState(true);

  const logout = () => {
    setUser(null);
    setToken('');
    setStoredToken('');
  };

  const validateToken = async (candidateToken) => {
    if (!candidateToken) {
      logout();
      return false;
    }

    try {
      const response = await fetch(`${apiUrl}/api/v1/auth/me`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${candidateToken}`,
        },
      });

      if (!response.ok) {
        logout();
        return false;
      }

      const data = await response.json();
      setUser(data?.user || null);
      setToken(candidateToken);
      setStoredToken(candidateToken);
      return true;
    } catch {
      logout();
      return false;
    }
  };

  const login = async (email, password) => {
    const response = await fetch(`${apiUrl}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data?.error || 'Login failed');
    }

    const nextToken = data?.token || '';
    if (!nextToken) {
      throw new Error('Missing token');
    }

    setUser(data?.user || null);
    setToken(nextToken);
    setStoredToken(nextToken);
    return data;
  };

  useEffect(() => {
    let mounted = true;

    const bootstrap = async () => {
      const existing = getStoredToken();
      if (!existing) {
        if (mounted) setLoading(false);
        return;
      }

      await validateToken(existing);
      if (mounted) setLoading(false);
    };

    bootstrap();
    return () => {
      mounted = false;
    };
  }, [apiUrl]);

  const value = useMemo(() => ({
    user,
    token,
    loading,
    authenticated: Boolean(user && token),
    login,
    logout,
    validateToken,
  }), [user, token, loading]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
