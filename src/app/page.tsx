'use client'

import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

export default function Home() {
  const { data: session } = useSession()
  const router = useRouter()

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
            Formaton
          </h1>
          <p className="text-xl text-gray-600 mb-8">
            Deploy your applications to AWS ECS with ease
          </p>
          <div className="space-x-4">
            <button 
              onClick={handleGetStarted}
              className="bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 transition-colors cursor-pointer"
            >
              Get Started
            </button>
            <Link
              href="/api/auth/signin"
              className="border border-gray-300 text-gray-700 px-6 py-3 rounded-lg hover:bg-gray-50 transition-colors inline-block"
            >
              Learn More
            </Link>
          </div>
        </div>
      </div>
    </main>
  )
}