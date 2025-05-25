import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const session = await getServerSession(authOptions)
    
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    // Get deployment and verify ownership
    const deployment = await prisma.deployment.findFirst({
      where: {
        id: params.id,
        project: {
          userId: session.user.id
        }
      },
      include: {
        project: true
      }
    })

    if (!deployment) {
      return NextResponse.json({ error: 'Deployment not found' }, { status: 404 })
    }

    return NextResponse.json({
      logs: deployment.logs || '',
      status: deployment.status,
      updatedAt: deployment.updatedAt
    })
  } catch (error) {
    console.error('Error fetching deployment logs:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}