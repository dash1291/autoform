import { NextAuthOptions } from 'next-auth'
import { PrismaAdapter } from '@next-auth/prisma-adapter'
import GitHubProvider from 'next-auth/providers/github'
import { prisma } from './prisma'

export const authOptions: NextAuthOptions = {
  adapter: PrismaAdapter(prisma),
  providers: [
    GitHubProvider({
      clientId: process.env.GITHUB_ID!,
      clientSecret: process.env.GITHUB_SECRET!,
      authorization: {
        params: {
          scope: 'read:user user:email repo',
        },
      },
      allowDangerousEmailAccountLinking: true,
    }),
  ],
  callbacks: {
    session: async ({ session, user, token }) => {
      // For database strategy, user object is available
      if (session?.user && user?.id) {
        session.user.id = user.id
        
        // Retrieve GitHub access token from database
        const account = await prisma.account.findFirst({
          where: {
            userId: user.id,
            provider: 'github',
          },
        })
        
        console.log('Access token exists:', !!account?.access_token)
        console.log('Access token length:', account?.access_token?.length || 0)
        console.log('Refresh token exists:', !!account?.refresh_token)
        console.log('Full account object:', JSON.stringify(account, null, 2))
        
        if (account?.access_token) {
          session.accessToken = account.access_token
        }
      }
      // Fallback for JWT strategy
      else if (session?.user && token?.sub) {
        session.user.id = token.sub
      }
      return session
    },
    jwt: async ({ user, token, account }) => {
      if (user) {
        token.uid = user.id
      }
      if (account && account.access_token) {
        token.accessToken = account.access_token
      }
      return token
    },
    async signIn({ user, account, profile }) {
      // Log the account object during sign in to debug
      console.log('Sign in account object:', JSON.stringify(account, null, 2))
      
      // Ensure access token is preserved during sign in
      if (account && account.access_token) {
        console.log('Access token found during sign in, ensuring it gets stored')
        // The PrismaAdapter should handle this automatically, but let's log it
      }
      
      return true
    },
  },
  events: {
    async linkAccount({ user, account, profile }) {
      console.log('Account linked:', {
        provider: account.provider,
        hasAccessToken: !!account.access_token,
        accessTokenLength: account.access_token?.length || 0,
        hasRefreshToken: !!account.refresh_token,
        tokenType: account.token_type,
        scope: account.scope
      })
    },
    async createUser({ user }) {
      console.log('User created:', user.id)
    }
  },
  session: {
    strategy: 'database',
  },
}