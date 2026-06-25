import { useCallback, useEffect, useState } from 'react'
import { authApi, setUnauthorizedHandler, type MeResponse } from '../api'
import Login from '../pages/Login'
import { AuthContext } from './useAuth'

export default function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<MeResponse | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      setState(await authApi.me())
    } catch {
      setState({ auth_enabled: true, authenticated: false, username: null })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  // 세션 만료(임의 API 401) 시 로그인 화면으로 전환.
  useEffect(() => {
    setUnauthorizedHandler(() =>
      setState((s) => (s ? { ...s, authenticated: false, username: null } : s)),
    )
    return () => setUnauthorizedHandler(null)
  }, [])

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } catch {
      /* 무시 */
    }
    setState((s) => (s ? { ...s, authenticated: false, username: null } : s))
  }, [])

  if (loading || !state) {
    return <div className="min-h-screen flex items-center justify-center text-muted">불러오는 중…</div>
  }

  if (state.auth_enabled && !state.authenticated) {
    return <Login onLoggedIn={refresh} />
  }

  return (
    <AuthContext.Provider value={{ username: state.username, authEnabled: state.auth_enabled, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
