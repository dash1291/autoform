'use client'

import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/lib/auth-client'
import { signIn, signOut } from 'next-auth/react'
import { Spinner } from '@/components/ui/spinner'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

export default function Navbar() {
  const { user, isAuthenticated, isLoading } = useAuth()

  return (
    <nav className="bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 border-b border-gray-700">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center">
            <Link href="/" className="text-xl font-bold text-foreground">
              Autoform
            </Link>
          </div>
          
          <div className="flex items-center space-x-4">
            {isLoading ? (
              <div className="text-muted-foreground flex items-center gap-2">
                <span>Signing In</span>
                <Spinner size="sm" color="secondary" />
              </div>
            ) : isAuthenticated && user ? (
              <>
                <div className="flex items-center space-x-3">
                  <Link href="/docs">
                    <Button variant="ghost" className="text-foreground hover:text-foreground">
                      Documentation
                    </Button>
                  </Link>
                  <div className="border-l pl-3 ml-3">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button className="flex items-center space-x-2 rounded-md px-2 py-1.5 hover:bg-accent focus:outline-none focus:ring-1 focus:ring-ring">
                          <img
                            className="h-8 w-8 rounded-full"
                            src={user.image || ''}
                            alt={user.name || ''}
                          />
                          <span className="text-sm text-foreground">{user.name}</span>
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-56">
                        <DropdownMenuItem asChild>
                          <Link href="/dashboard">
                            Projects
                          </Link>
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem 
                          onClick={() => signOut()}
                          className="text-destructive focus:text-destructive"
                        >
                          Sign out
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              </>
            ) : (
              <Button 
                onClick={() => signIn('github')}
                className="bg-primary"
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