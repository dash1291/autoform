'use client'

import { signIn, signOut, useSession } from 'next-auth/react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { ThemeToggle } from '@/components/theme-toggle'

export default function Navbar() {
  const { data: session, status } = useSession()

  return (
    <nav className="bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 border-b">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center">
            <Link href="/" className="text-xl font-bold text-foreground">
              Autoform
            </Link>
          </div>
          
          <div className="flex items-center space-x-4">
            <ThemeToggle />
            {status === 'loading' ? (
              <div className="text-muted-foreground">Loading...</div>
            ) : session ? (
              <>
                <div className="flex items-center space-x-3">
                  <img
                    className="h-8 w-8 rounded-full"
                    src={session.user?.image || ''}
                    alt={session.user?.name || ''}
                  />
                  <span className="text-sm text-foreground">{session.user?.name}</span>
                  <Button
                    variant="ghost"
                    onClick={() => signOut()}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    Sign out
                  </Button>
                </div>
              </>
            ) : (
              <Button
                onClick={() => signIn('github')}
                className="bg-primary text-primary-foreground hover:bg-primary/90"
              >
                Sign in with GitHub
              </Button>
            )}
          </div>
        </div>
      </div>
    </nav>
  )
}