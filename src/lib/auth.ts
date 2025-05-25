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
    }),
  ],
  callbacks: {
    session: async ({ session, user, token }) => {
      // For database strategy, user object is available
      if (session?.user && user?.id) {
        session.user.id = user.id
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
      return true
    },
  },
  events: {},
  session: {
    strategy: 'database',
  },
}