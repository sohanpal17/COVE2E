import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, tokenStore } from '../services/api'
import type { UserOut } from '../types/api'

interface AuthCtx {
  user: UserOut | null
  loading: boolean
  login: (demoCode: string, language?: string) => Promise<UserOut>
  logout: () => void
  refresh: () => Promise<void>
}

const Ctx = createContext<AuthCtx>({ user: null, loading: true, login: async () => ({} as UserOut), logout: () => {}, refresh: async () => {} })

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    if (!tokenStore.get()) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      setUser(await api.me())
    } catch {
      tokenStore.clear()
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const login = useCallback(async (demoCode: string, language?: string) => {
    const res = await api.demoLogin(demoCode, language)
    tokenStore.set(res.access_token)
    setUser(res.user)
    return res.user
  }, [])

  const logout = useCallback(() => {
    tokenStore.clear()
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, loading, login, logout, refresh }), [user, loading, login, logout, refresh])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)
