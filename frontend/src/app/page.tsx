'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth-client'
import { signIn } from 'next-auth/react'
import { Github, PackageOpen, Zap, Users, Copy, Cloud, Trees, ArrowRight, CheckCircle, Logs, Expand } from 'lucide-react'

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

  const features = [
    {
      icon: PackageOpen,
      title: "Easy Setup",
      description: "Autoform makes it extremely easy to get your application up and running on AWS ECS. Quickly bootstrap with best practices without having to deep-diving into AWS concepts and setting up your own tooling. Let Autoform do it for you while you focus on your application.",
      iconColor: "text-orange-600",
      iconBg: "bg-orange-50"
    },
    {
      icon: Expand,
      title: "Ready to Scale",
      description: "Autoform makes your application ready to scale when the traffic arrives. You can scale your application automatically based on industry standards or control it yourself.",
      iconColor: "text-purple-600",
      iconBg: "bg-purple-100"
    },
    {
      icon: Logs,
      title: "Integrated Logging",
      description: "Easily view the logs of your running application to stay on top of the application health and debug issues.",
      iconColor: "text-purple-600",
      iconBg: "bg-purple-100"
    },
    {
      icon: Zap,
      title: "Fast Automated Deployments",
      description: "Connect your GitHub repository and deploy on every push. From code to live application in minutes without the need to setup your own deployment pipelines.",
      iconColor: "text-blue-600",
      iconBg: "bg-blue-100"
    },
    {
      icon: Copy,
      title: "Multiple Environments",
      description: "Seamlessly deploy your application across different environments. Your production environment stays safe while you can test your features in preview environment.",
      iconColor: "text-purple-600",
      iconBg: "bg-purple-100"
    },
  
    {
      icon: Users,
      title: "Team Collaboration",
      description: "Share projects and environments with your team within Autoform. Built-in access controls and deployment history for better collaboration. No need to manage the complexity of AWS IAM roles and policies.",
      iconColor: "text-green-600",
      iconBg: "bg-green-50"
    }
  ]

  return (
    <main className="min-h-screen bg-gradient-to-br">
      {/* Hero Section */}
      <section className="pt-32 pb-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-5xl sm:text-6xl font-light font-montserrat text-foreground mb-6 leading-tight">
            Deploy to your cloud
            <br />
            <span className="text-muted-foreground">in minutes</span>
          </h1>
          <p className="text-xl text-muted-foreground mb-8 max-w-2xl mx-auto leading-relaxed">
            Autoform makes it easy to deploy applications to AWS so that developers can focus on building.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Button 
              onClick={handleGetStarted}
              className="bg-background text-foreground px-8 py-3"
            >
              Get Started
              <ArrowRight className="ml-2 h-5 w-5" />
            </Button>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 bg-muted/20">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="mb-16">
            <h2 className="text-2xl text-center font-normal text-foreground mb-8">
              Everything you need in a platform to move fast <span className="text-muted-foreground italic">without breaking things.</span>
            </h2>
          </div>
          
          <div className="space-y-16">
            {features.map((feature, index) => (
              <div key={index} className="flex flex-col w-3/4 md:flex-row items-start gap-8 mb-8">
                 <span>
                    <feature.icon strokeWidth={1} className={`text-secondary w-12 h-12 rounded`} />
                  </span>
                <div className="flex-1">
                  <h3 className="text-2xl font-normal text-foreground mb-4">
                    {feature.title}
                  </h3>
                  <p className="text-lg text-muted-foreground leading-relaxed">
                    {feature.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>


      {/* CTA Section */}
      <section className="py-20 text-foreground border-t border-border">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="text-3xl font-normal mb-4">
            Ready to deploy?
          </h2>
          <p className="text-xl text-muted-foreground mb-8 max-w-2xl mx-auto">
            
          </p>
          <Button 
            onClick={handleGetStarted}
            className="bg-background text-foreground px-8 py-3"
          >
            Start Deploying Now
            <ArrowRight className="ml-2 h-5 w-5" />
          </Button>
        </div>
      </section>

      {/* Footer */}
      <footer className="borderborder-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center text-muted-foreground">
            <p>&copy; 2025 Autoform. Built for developers who ship fast.</p>
          </div>
        </div>
      </footer>
    </main>
  )
}