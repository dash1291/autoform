'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { useJwtStore } from '@/lib/auth-client'

export default function Home() {
  const { jwtToken } = useJwtStore()
  const router = useRouter()

  // Redirect to dashboard if user is logged in
  useEffect(() => {
    if (jwtToken) {
      router.push('/dashboard')
    }
  }, [jwtToken, router])

  const handleGetStarted = () => {
    if (jwtToken) {
      router.push('/dashboard')
    } else {
      // Redirect to login page or show login form
      window.location.href = '/auth/login'
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
              asChild
              variant="outline"
              size="lg"
            >
              <Link href="/auth/login">
                Login
              </Link>
            </Button>
          </div>
        </div>
      </div>
    </main>
  )
}