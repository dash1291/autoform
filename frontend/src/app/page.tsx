'use client'

import { useRouter } from 'next/navigation'
import Link from 'next/link'
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



  return (
    <main className="bg-gradient-to-br">
      {/* Hero Section */}
      <section className="pt-32 pb-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-5xl sm:text-6xl font-light font-montserrat text-foreground mb-6 leading-tight">
            The simplest way
            <br />
            <span className="text-muted-foreground">to deploy on AWS</span>
          </h1>
          <p className="text-xl text-muted-foreground mb-8 max-w-2xl mx-auto leading-relaxed">
            No Terraform. No Kubernetes. No DevOps effort needed. Just push your code and ship in minutes. Get seamless developer experience at AWS prices.
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
            <h2 className="text-2xl text-left font-normal text-foreground mb-8">
              Everything you need in a platform to move fast <span className="text-muted-foreground italic">without breaking things.</span>
            </h2>
          </div>
          
          <div className="space-y-16">
            {/* Easy Setup */}
            <div className="flex flex-row w-full items-start gap-8 mb-8">
              <span>
                <PackageOpen strokeWidth={1} className="text-secondary w-12 h-12 rounded" />
              </span>
              <div className="flex-1">
                <h3 className="text-2xl font-normal text-foreground mb-2">
                  Production-ready in 5 minutes
                </h3>
                <p className="text-lg text-muted-foreground leading-relaxed">
                  What takes days with Terraform takes minutes with Autoform. Connect your repo, pick your AWS account, deploy. That's it.
                </p>
              </div>
            </div>

            {/* Ready to Scale */}
            <div className="flex flex-row w-full items-start gap-8 mb-8">
              <span className="inline-block w-auto">
                <Expand strokeWidth={1} className="text-secondary w-12 h-12 rounded" />
              </span>
              <div className="flex-1">
                <h3 className="text-2xl font-normal text-foreground mb-2">
                  Scales automatically, bills reasonably
                </h3>
                <p className="text-lg text-muted-foreground leading-relaxed">
                  Your app scales to handle viral traffic without the viral bill. Auto-scaling that actually works, configured from day one.
                </p>
              </div>
            </div>

            {/* Fast Automated Deployments */}
            <div className="flex flex-row w-full items-start gap-8 mb-8">
              <span>
                <Zap strokeWidth={1} className="text-secondary w-12 h-12 rounded" />
              </span>
              <div className="flex-1">
                <h3 className="text-2xl font-normal text-foreground mb-2">
                  Push code, ship instantly
                </h3>
                <p className="text-lg text-muted-foreground leading-relaxed">
                  Every commit automatically deployed. No build pipelines to configure. No deploy buttons to push. It just works.
                </p>
              </div>
            </div>

            {/* Multiple Environments */}
            <div className="flex flex-row w-full items-start gap-8 mb-8">
              <span>
                <Copy strokeWidth={1} className="text-secondary w-12 h-12 rounded" />
              </span>
              <div className="flex-1">
                <h3 className="text-2xl font-normal text-foreground mb-2">
                  Dev, staging, prod - simplified
                </h3>
                <p className="text-lg text-muted-foreground leading-relaxed">
                  Spin up unlimited environments with one click. Test safely. Ship confidently. No extra DevOps work needed.
                </p>
              </div>
            </div>

            {/* Integrated Logging */}
            <div className="flex flex-row w-full items-start gap-8 mb-8">
              <span>
                <Logs strokeWidth={1} className="text-secondary w-12 h-12 rounded" />
              </span>
              <div className="flex-1">
                <h3 className="text-2xl font-normal text-foreground mb-2">
                  Your logs, where you need them
                </h3>
                <p className="text-lg text-muted-foreground leading-relaxed">
                  Application logs right in your dashboard. No CloudWatch spelunking. No third-party tools. Just instant visibility.
                </p>
              </div>
            </div>
          </div>
          <div className="mt-16 max-w-4xl mx-auto">
            <p className="text-2xl text-left font-normal text-foreground mb-6">
              Get modern developer experience (like Heroku, Vercel, Railway) <span className="text-muted-foreground">at 80-90% lower cost.</span>
            </p>
            <p className="text-2xl text-left font-normal text-foreground">
              All the other perks of AWS - scale, control, and compliance.
            </p>
            <p className="text-2xl text-left font-normal text-muted-foreground mb-8">None of the complexity.</p>
          </div>
        </div>
      </section>


      {/* CTA Section */}
      <section className="py-20 text-foreground border-t border-border/50">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="text-2xl font-normal mb-4">
            Deploy your next app in 5 minutes
          </h2>
          <p className="text-lg text-muted-foreground mb-8 max-w-2xl mx-auto">
            Join developers who spend more time building and less time wrangling deployment pipelines. We'll help you migrate.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Button 
              onClick={handleGetStarted}
              className="bg-background text-foreground px-8 py-3"
            >
              Start Deploying
              <ArrowRight className="ml-2 h-5 w-5" />
            </Button>
            <Link 
              href="https://calendly.com/ashish-dubey91/30min"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Button 
                variant="outline"
                className="px-8 py-3"
              >
                Get Migration Help
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="borderborder-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center text-sm text-muted-foreground">
            <p>&copy; 2025 Autoform. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </main>
  )
}