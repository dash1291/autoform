'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from '@/lib/auth-client'
import { signIn } from 'next-auth/react'
import { Github, Zap, Users, Cloud } from 'lucide-react'

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
    <main className="min-h-screen bg-gradient-to-br">
      {/* Hero Section */}
      <div className="container mx-auto px-4 py-16">
        <div className="text-center mb-16">
          <h1 className="text-5xl font-bold text-gray-900 mb-6">
            Autoform
          </h1>
          <p className="text-2xl text-gray-600 mb-8 max-w-3xl mx-auto">
            Deploy your applications to AWS ECS with ease. From GitHub to production in minutes.
          </p>
          <div className="space-x-4">
            <Button 
              onClick={handleGetStarted}
              size="lg"
              className="bg-blue-600 hover:bg-blue-700"
            >
              <Github className="mr-2 h-5 w-5" />
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

        {/* Features Section */}
        <div className="mb-16">
          <h2 className="text-3xl font-bold text-center text-gray-900 mb-12">
            Why Choose Autoform?
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            <Card className="bg-white/50 border-0">
              <CardHeader>
                <div className="w-12 h-12 bg-orange-100 rounded-lg flex items-center justify-center mb-4">
                  <Cloud className="h-6 w-6 text-orange-600" />
                </div>
                <CardTitle>AWS Native</CardTitle>
                <CardDescription>
                  Built specifically for AWS ECS. Quickly bootstrap with best practices. Scale infinitely.
                </CardDescription>
              </CardHeader>
            </Card>

            <Card className="bg-white/50 border-0">
              <CardHeader>
                <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mb-4">
                  <Zap className="h-6 w-6 text-blue-600" />
                </div>
                <CardTitle>Fast Deployments</CardTitle>
                <CardDescription>
                  Connect your GitHub repo and deploy to AWS ECS in minutes.
                </CardDescription>
              </CardHeader>
            </Card>


            <Card className="bg-white/50 border-0">
              <CardHeader>
                <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mb-4">
                  <Users className="h-6 w-6 text-purple-600" />
                </div>
                <CardTitle>Team Collaboration</CardTitle>
                <CardDescription>
                  Work with your team seamlessly. Share projects, manage permissions, and deploy together.
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        </div>

        {/* Call to Action */}
        <div className="text-center bg-white rounded-lg shadow-lg p-8">
          <h3 className="text-2xl font-bold text-gray-900 mb-4">
            Ready to Deploy?
          </h3>
          <p className="text-gray-600 mb-6">
            Get started with Autoform now and deploy your application to AWS ECS in minutes.
          </p>
          <Button 
            onClick={handleGetStarted}
            size="lg"
            className="bg-blue-600 hover:bg-blue-700"
          >
            <Github className="mr-2 h-5 w-5" />
            Start Deploying Now
          </Button>
        </div>
      </div>
    </main>
  )
}