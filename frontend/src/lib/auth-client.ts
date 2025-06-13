import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { useSession } from 'next-auth/react'
import { useEffect } from 'react'

interface AuthTokenStore {
  jwtToken: string | null
  setJwtToken: (token: string | null) => void
  clearJwtToken: () => void
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Store for JWT token from Python backend
export const useJwtStore = create<AuthTokenStore>()(
  persist(
    (set) => ({
      jwtToken: null,
      setJwtToken: (token) => set({ jwtToken: token }),
      clearJwtToken: () => set({ jwtToken: null }),
    }),
    {
      name: 'jwt-storage',
    }
  )
)

// Helper hook that combines NextAuth session with JWT token
export const useAuth = () => {
  const { data: session, status } = useSession()
  const { jwtToken, setJwtToken, clearJwtToken } = useJwtStore()

  // Exchange NextAuth session for JWT token when session changes
  useEffect(() => {
    if (session?.user && !jwtToken) {
      exchangeSessionForJwt()
    } else if (!session && jwtToken) {
      clearJwtToken()
    }
  }, [session, jwtToken])

  const exchangeSessionForJwt = async () => {
    try {
      console.log('Exchanging session for JWT...', {
        hasSession: !!session,
        hasUser: !!session?.user,
        userEmail: session?.user?.email,
        hasAccessToken: !!session?.accessToken
      })

      const response = await fetch(`${API_BASE_URL}/api/auth/exchange-session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          sessionUser: session?.user,
          accessToken: session?.accessToken,
        }),
      })

      console.log('Session exchange response:', response.status)

      if (response.ok) {
        const data = await response.json()
        console.log('JWT token received:', !!data.access_token)
        setJwtToken(data.access_token)
      } else {
        const error = await response.text()
        console.error('Session exchange failed:', response.status, error)
      }
    } catch (error) {
      console.error('Failed to exchange session for JWT:', error)
    }
  }

  const getAuthHeaders = (): HeadersInit => {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }

    if (jwtToken) {
      headers.Authorization = `Bearer ${jwtToken}`
    }

    return headers
  }

  return {
    user: session?.user || null,
    isAuthenticated: !!session,
    isLoading: status === 'loading',
    jwtToken,
    getAuthHeaders,
    refreshJwtToken: exchangeSessionForJwt,
  }
}