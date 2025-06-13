import { NextAuthOptions } from 'next-auth'
import GitHubProvider from 'next-auth/providers/github'

export const authOptions: NextAuthOptions = {
  providers: [
    GitHubProvider({
      clientId: process.env.GITHUB_ID!,
      clientSecret: process.env.GITHUB_SECRET!,
      authorization: {
        params: {
          scope: 'read:user user:email repo',
        },
      },
    }),
  ],
  callbacks: {
    session: async ({ session, token }) => {
      try {
        // For JWT strategy, token object is available
        if (session?.user && token?.sub) {
          session.user.id = token.sub as string
        }
        
        // Include GitHub access token in session
        if (token?.accessToken) {
          session.accessToken = token.accessToken as string
        }
        
        return session
      } catch (error) {
        console.error('Session callback error:', error)
        return session
      }
    },
    jwt: async ({ user, token, account }) => {
      try {
        // Store user ID in token
        if (user?.id) {
          token.sub = user.id
        }
        
        // Store GitHub access token in token
        if (account?.access_token) {
          token.accessToken = account.access_token
        }
        
        return token
      } catch (error) {
        console.error('JWT callback error:', error)
        return token
      }
    },
    async signIn({ user, account, profile }) {
      try {
        console.log('GitHub sign in:', {
          provider: account?.provider,
          hasAccessToken: !!account?.access_token,
          userEmail: user?.email,
        })
        
        return true
      } catch (error) {
        console.error('Sign in error:', error)
        return false
      }
    },
  },
  session: {
    strategy: 'jwt',
    maxAge: 30 * 24 * 60 * 60, // 30 days
  },
  jwt: {
    maxAge: 30 * 24 * 60 * 60, // 30 days
  },
  debug: process.env.NODE_ENV === 'development',
}