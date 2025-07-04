'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from '@/lib/auth-client'
import { signIn } from 'next-auth/react'
import { Github, Zap, Users, Copy, Cloud, Trees } from 'lucide-react'

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
      <div className="container w-full md:w-3/4 mx-auto px-4 py-16">
        <div className="text-center mb-16 mt-16">
          <div className="text-3xl font-light font-montserrat text-foreground mb-10 max-w-3xl mx-auto">
            <p>
              Deploy your applications to AWS ECS with ease.
            </p>
            <p className="mt-2">
              From GitHub to production in minutes.
            </p>
          </div>
          <div className="space-x-4">
            <Button 
              onClick={handleGetStarted}
              size="lg"
              className="bg-background text-foreground"
            >
              Get Started
            </Button>
          </div>
        </div>

        {/* Features Section */}
        <div className="mb-16">
          <h2 className="text-3xl font-bold text-center text-foreground mb-12">
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            <Card className="border-0 border-r">
              <CardHeader>
                <div className="w-12 h-12 bg-orange-50 rounded-lg flex items-center justify-center mb-4">
                  <Cloud className="h-6 w-6 text-orange-600" />
                </div>
                <CardTitle>AWS Native</CardTitle>
                <CardDescription>
                  Built specifically for AWS ECS. Quickly bootstrap with best practices. Scale infinitely.
                </CardDescription>
              </CardHeader>
            </Card>

            <Card className="border-0 border-r">
              <CardHeader>
                <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mb-4">
                  <Zap className="h-6 w-6 text-blue-600" />
                </div>
                <CardTitle>Fast Automated Deployments</CardTitle>
                <CardDescription>
                  Connect your GitHub repo and deploy to AWS ECS on every push
                </CardDescription>
              </CardHeader>
            </Card>


            <Card className="border-0">
              <CardHeader>
                <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mb-4">
                  <Copy className="h-6 w-6 text-purple-600" />
                </div>
                <CardTitle>Environments</CardTitle>
                <CardDescription>
                  Seemlessly deploy your application in different environments for testing
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        </div>

        {/* Call to Action */}
        <div className="text-center text-foreground rounded p-8 border-t w-full border-border mx-auto">
          <h3 className="text-lg font-semibold mb-4">
            Ready to Deploy?
          </h3>
          <p className="mb-6 text-sm">
            Get started with Autoform now and deploy your application to AWS ECS in minutes.
          </p>
          <Button 
            onClick={handleGetStarted}
            size="lg"
            className="bg-background text-foreground"
            >
            Start Deploying Now
          </Button>
        </div>
      </div>
    </main>
  )
}