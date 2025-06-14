'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth-client'
import { signIn } from 'next-auth/react'

export default function Home() {
  const { isAuthenticated, isLoading } = useAuth()
  const router = useRouter()

  // Redirect to dashboard if user is logged in
  useEffect(() => {
    if (isAuthenticated && !isLoading) {
      router.push('/dashboard')
    }
  }, [isAuthenticated, isLoading, router])

  const handleGetStarted = () => {
    if (isAuthenticated) {
      router.push('/dashboard')
    } else {
      signIn('github')
    }
  }

  return (
    <main className="min-h-screen bg-gray-50">
      <div className="container mx-auto px-4 py-16">
        <div className="text-center">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">
            Autoform
          </h1>
          <p className="text-xl text-gray-600 mb-8">
            Deploy your applications to AWS ECS with ease
          </p>
          <div className="space-x-4">
            <Button 
              onClick={handleGetStarted}
              size="lg"
            >
              Get Started
            </Button>
            <Button
              onClick={() => signIn('github')}
              variant="outline"
              size="lg"
            >
              Login
            </Button>
          </div>
        </div>
      </div>
    </main>
  )
}