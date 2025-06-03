'use client'

import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'

export default function Home() {
  const { data: session } = useSession()
  const router = useRouter()

  // Redirect to dashboard if user is logged in
  useEffect(() => {
    if (session) {
      router.push('/dashboard')
    }
  }, [session, router])

  const handleGetStarted = () => {
    if (session) {
      router.push('/dashboard')
    } else {
      router.push('/api/auth/signin')
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
              <Link href="/api/auth/signin">
                Learn More
              </Link>
            </Button>
          </div>
        </div>
      </div>
    </main>
  )
}