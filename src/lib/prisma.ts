import { PrismaClient } from '@prisma/client'

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined
}

export const prisma = globalForPrisma.prisma ?? new PrismaClient({
  datasources: {
    db: {
      url: process.env.DATABASE_URL,
    },
  },
  // Increase timeouts for better cloud connectivity
  log: process.env.NODE_ENV === 'development' ? ['error', 'warn'] : ['error'],
})

// Set connection pool timeout
if (globalForPrisma.prisma) {
  globalForPrisma.prisma.$connect()
}

if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = prisma