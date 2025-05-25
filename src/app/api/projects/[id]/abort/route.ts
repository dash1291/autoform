import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'
import { ProjectStatus, DeploymentStatus } from '@/types'
import { deploymentManager } from '@/lib/deploymentManager'

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const session = await getServerSession(authOptions)
    
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    // Check if project exists and belongs to user
    const project = await prisma.project.findFirst({
      where: {
        id: params.id,
        userId: session.user.id,
      },
    })

    if (!project) {
      return NextResponse.json({ error: 'Project not found' }, { status: 404 })
    }

    // Check if project is actually deploying
    const deployableStatuses = [
      ProjectStatus.CLONING,
      ProjectStatus.BUILDING,
      ProjectStatus.DEPLOYING
    ]

    if (!deployableStatuses.includes(project.status as ProjectStatus)) {
      return NextResponse.json(
        { error: 'No active deployment to abort' }, 
        { status: 400 }
      )
    }

    // Find the current deployment
    const currentDeployment = await prisma.deployment.findFirst({
      where: {
        projectId: project.id,
        status: {
          in: [
            DeploymentStatus.PENDING,
            DeploymentStatus.BUILDING,
            DeploymentStatus.PUSHING,
            DeploymentStatus.PROVISIONING,
            DeploymentStatus.DEPLOYING
          ]
        }
      },
      orderBy: {
        createdAt: 'desc'
      }
    })

    // Update project status to FAILED
    await prisma.project.update({
      where: {
        id: project.id,
      },
      data: {
        status: ProjectStatus.FAILED,
      },
    })

    // Update deployment status to FAILED if it exists
    if (currentDeployment) {
      await prisma.deployment.update({
        where: {
          id: currentDeployment.id,
        },
        data: {
          status: DeploymentStatus.FAILED,
          logs: (currentDeployment.logs || '') + '\n\n--- DEPLOYMENT ABORTED BY USER ---',
        },
      })
    }

    // Signal the deployment manager to abort the deployment
    deploymentManager.markAsAborted(project.id)
    
    console.log(`Deployment aborted for project ${project.name} by user ${session.user.id}`)

    return NextResponse.json({ 
      message: 'Deployment aborted successfully',
      project: {
        ...project,
        status: ProjectStatus.FAILED
      }
    })
  } catch (error) {
    console.error('Error aborting deployment:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}