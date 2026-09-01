import { createContext, PropsWithChildren, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { get, post, setToken, getToken, resolveApiOrigin } from '@/lib/api';

type AuthState = {
  ready: boolean;
  user: any | null;
  origin: string;
  login: (username: string, password: string) => Promise<any>;
  acceptAuth: (payload: any) => Promise<void>;
  refreshUser: () => Promise<any>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<any | null>(null);
  const [origin, setOrigin] = useState('');

  const refreshUser = useCallback(async () => {
    const me = await get<any>('/api/auth/me');
    setUser(me);
    return me;
  }, []);

  const acceptAuth = useCallback(async (payload: any) => {
    if (!payload?.token) throw new Error('로그인 토큰이 반환되지 않았습니다.');
    await setToken(payload.token);
    setUser(payload.user || null);
    if (!payload.user) await refreshUser();
  }, [refreshUser]);

  const login = useCallback(async (username: string, password: string) => {
    const payload = await post<any>('/api/auth/login', { username, password }, false);
    await acceptAuth(payload);
    return payload;
  }, [acceptAuth]);

  const logout = useCallback(async () => {
    await setToken('');
    setUser(null);
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const selected = await resolveApiOrigin(true);
        if (alive) setOrigin(selected);
        const token = await getToken();
        if (token) {
          try { await refreshUser(); } catch { await setToken(''); }
        }
      } finally {
        if (alive) setReady(true);
      }
    })();
    return () => { alive = false; };
  }, [refreshUser]);

  const value = useMemo(() => ({ ready, user, origin, login, acceptAuth, refreshUser, logout }), [ready, user, origin, login, acceptAuth, refreshUser, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
