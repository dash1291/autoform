'use client'

import { useAuth } from '@/lib/auth-client'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { Spinner } from '@/components/ui/spinner'

interface AuthGuardProps {
  children: React.ReactNode
}

export default function AuthGuard({ children }: AuthGuardProps) {
  const { isAuthenticated, isLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/')
    }
  }, [isAuthenticated, isLoading, router])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Spinner />
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <div className="text-center py-12">
        <h1 className="text-xl font-semibold mb-4">Please sign in</h1>
        <p className="text-gray-600">You need to be signed in to access the documentation.</p>
      </div>
    )
  }

  return <>{children}</>
}