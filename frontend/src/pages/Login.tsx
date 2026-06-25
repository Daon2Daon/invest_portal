import { useState } from 'react'
import { authApi } from '../api'

export default function Login({ onLoggedIn }: { onLoggedIn: () => void | Promise<void> }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await authApi.login(username, password)
      await onLoggedIn()
    } catch (err) {
      setError((err as Error).message || '로그인에 실패했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4">
        <h1 className="text-xl font-bold">💰 invest 로그인</h1>
        {error && (
          <p className="text-sm text-down border border-border rounded-lg px-3 py-2">{error}</p>
        )}
        <div>
          <label className="block text-sm text-muted mb-1">아이디</label>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            autoComplete="username"
            className="input w-full"
          />
        </div>
        <div>
          <label className="block text-sm text-muted mb-1">비밀번호</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            className="input w-full"
          />
        </div>
        <button type="submit" disabled={busy || !username || !password} className="btn btn-primary w-full">
          {busy ? '로그인 중...' : '로그인'}
        </button>
      </form>
    </div>
  )
}
