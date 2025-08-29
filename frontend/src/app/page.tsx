'use client'

import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth-client'
import { signIn } from 'next-auth/react'
import { Github, PackageOpen, Zap, Users, Copy, Cloud, Trees, ArrowRight, CheckCircle, Logs, Expand } from 'lucide-react'
import { motion } from 'framer-motion'

// Animation configurations - all using the same fade-up with viewport trigger
const animations = {
  fadeUpViewport: {
    initial: { opacity: 0, y: 20 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true, amount: 0.3 },
    transition: { duration: 0.6 }
  },
  scaleOnHover: {
    whileHover: { scale: 1.05 },
    whileTap: { scale: 0.95 }
  }
}

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
        <motion.div 
          className="max-w-4xl mx-auto text-center"
          {...animations.fadeUpViewport}
        >
          <motion.h1 
            className="text-5xl sm:text-6xl font-light font-montserrat text-foreground mb-6 leading-tight"
            {...animations.fadeUpViewport}
          >
            The simplest way
            <br />
            <span className="text-muted-foreground">to deploy on AWS</span>
          </motion.h1>
          <motion.p 
            className="text-xl text-muted-foreground mb-8 max-w-2xl mx-auto leading-relaxed"
            {...animations.fadeUpViewport}
          >
            Deploy on your cloud without compromising on developer experience and spending precious engineering cycles. No Terraform. No Kubernetes. No deployment pipelines. Just push your code and ship in minutes.
          </motion.p>
          <motion.div 
            className="flex flex-col sm:flex-row gap-4 justify-center"
            {...animations.fadeUpViewport}
          >
            <motion.div
              {...animations.scaleOnHover}
            >
              <Button 
                onClick={handleGetStarted}
                className="bg-background text-foreground px-8 py-3"
              >
                Get Started
                <ArrowRight className="ml-2 h-5 w-5" />
              </Button>
            </motion.div>
          </motion.div>
        </motion.div>
      </section>

      {/* Features Section */}
      <section className="py-20 bg-muted/20">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <motion.div 
            className="mb-16"
            {...animations.fadeUpViewport}
          >
            <h2 className="text-2xl text-left font-normal text-foreground mb-8">
              Everything you need in a platform to move fast <span className="text-muted-foreground italic">without breaking things.</span>
            </h2>
          </motion.div>
          
          <div className="space-y-16">
            {/* Easy Setup */}
            <motion.div 
              className="flex flex-row w-full items-start gap-8 mb-8"
              {...animations.fadeUpViewport}
            >
              <span>
                <PackageOpen strokeWidth={1} className="text-secondary w-12 h-12 rounded" />
              </span>
              <div className="flex-1">
                <h3 className="text-2xl font-normal text-foreground mb-2">
                  Production-ready in 5 minutes
                </h3>
                <p className="text-lg text-muted-foreground leading-relaxed">
                  What takes days with IaC tools like Terraform takes minutes with Autoform. Connect your repo, configure your AWS account, deploy. That's it.
                </p>
              </div>
            </motion.div>

            {/* Ready to Scale */}
            <motion.div 
              className="flex flex-row w-full items-start gap-8 mb-8"
              {...animations.fadeUpViewport}
            >
              <span className="inline-block w-auto">
                <Expand strokeWidth={1} className="text-secondary w-12 h-12 rounded" />
              </span>
              <div className="flex-1">
                <h3 className="text-2xl font-normal text-foreground mb-2">
                  Scales automatically, bills reasonably
                </h3>
                <p className="text-lg text-muted-foreground leading-relaxed">
                  Whether it's a hobby project or serving millions of users, Autoform sets up your service that is ready for any scale, in a cost-effective manner.
                </p>
              </div>
            </motion.div>

            {/* Fast Automated Deployments */}
            <motion.div 
              className="flex flex-row w-full items-start gap-8 mb-8"
              {...animations.fadeUpViewport}
            >
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
            </motion.div>

            {/* Multiple Environments */}
            <motion.div 
              className="flex flex-row w-full items-start gap-8 mb-8"
              {...animations.fadeUpViewport}
            >
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
            </motion.div>

            {/* Integrated Logging */}
            <motion.div 
              className="flex flex-row w-full items-start gap-8 mb-8"
              {...animations.fadeUpViewport}
            >
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
            </motion.div>
          </div>
          <motion.div 
            className="mt-16 max-w-4xl mx-auto"
            {...animations.fadeUpViewport}
          >
            <motion.p 
              className="text-2xl text-left font-normal text-foreground mb-6"
              {...animations.fadeUpViewport}
            >
              Get modern developer experience (like Heroku, Vercel, Railway) <span className="text-muted-foreground">at 80-90% lower cost.</span>
            </motion.p>
            <motion.p 
              className="text-2xl text-left font-normal text-foreground"
              {...animations.fadeUpViewport}
            >
              All the other perks of AWS - scale, control, and compliance.
            </motion.p>
            <motion.p 
              className="text-2xl text-left font-normal text-muted-foreground mb-8"
              {...animations.fadeUpViewport}
            >
              None of the complexity.
            </motion.p>
          </motion.div>
        </div>
      </section>


      {/* CTA Section */}
      <section className="py-20 text-foreground border-t border-border/50">
        <motion.div 
          className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center"
          {...animations.fadeUpViewport}
        >
          <motion.h2 
            className="text-2xl font-normal mb-4"
            {...animations.fadeUpViewport}
          >
            Deploy your next app in 5 minutes
          </motion.h2>
          <motion.p 
            className="text-lg text-muted-foreground mb-8 max-w-2xl mx-auto"
            {...animations.fadeUpViewport}
          >
            Join developers who spend more time building and less time wrangling deployment pipelines. We'll help you migrate.
          </motion.p>
          <motion.div 
            className="flex flex-col sm:flex-row gap-4 justify-center"
            {...animations.fadeUpViewport}
          >
            <motion.div
              {...animations.scaleOnHover}
            >
              <Button 
                onClick={handleGetStarted}
                className="bg-background text-foreground px-8 py-3"
              >
                Start Deploying
                <ArrowRight className="ml-2 h-5 w-5" />
              </Button>
            </motion.div>
            <Link 
              href="https://calendly.com/ashish-dubey91/30min"
              target="_blank"
              rel="noopener noreferrer"
            >
              <motion.div
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                <Button 
                  variant="outline"
                  className="px-8 py-3"
                >
                  Get Migration Help
                </Button>
              </motion.div>
            </Link>
          </motion.div>
        </motion.div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center text-sm text-muted-foreground">
            <p>&copy; 2025 Autoform. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </main>
  )
}