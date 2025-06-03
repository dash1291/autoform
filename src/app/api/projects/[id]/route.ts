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

    const project = await prisma.project.findFirst({
      where: {
        id: params.id,
        userId: session.user.id,
      },
    })

    if (!project) {
      return NextResponse.json({ error: 'Project not found' }, { status: 404 })
    }

    return NextResponse.json(project)
  } catch (error) {
    console.error('Error fetching project:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const session = await getServerSession(authOptions)
    
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const body = await request.json()
    const { existingVpcId, existingSubnetIds, existingClusterArn, cpu, memory, diskSize, gitRepoUrl, branch } = body

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

    // Validate subnet IDs format if provided
    let subnetIdsJson = null
    if (existingSubnetIds) {
      try {
        // Ensure it's an array of strings
        const subnetArray = Array.isArray(existingSubnetIds) 
          ? existingSubnetIds 
          : existingSubnetIds.split(',').map((s: string) => s.trim())
        
        subnetIdsJson = JSON.stringify(subnetArray)
      } catch (error) {
        return NextResponse.json({ error: 'Invalid subnet IDs format' }, { status: 400 })
      }
    }

    // Validate resource configurations if provided
    if (cpu !== undefined && (cpu < 256 || cpu > 4096)) {
      return NextResponse.json(
        { error: 'CPU must be between 256 and 4096' },
        { status: 400 }
      )
    }
    
    if (memory !== undefined && (memory < 512 || memory > 30720)) {
      return NextResponse.json(
        { error: 'Memory must be between 512 and 30720 MB' },
        { status: 400 }
      )
    }
    
    if (diskSize !== undefined && (diskSize < 21 || diskSize > 200)) {
      return NextResponse.json(
        { error: 'Disk size must be between 21 and 200 GB' },
        { status: 400 }
      )
    }

    // Validate Git repository URL if provided
    if (gitRepoUrl !== undefined) {
      const gitUrlRegex = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+(?:\.git)?$/
      if (gitRepoUrl && !gitUrlRegex.test(gitRepoUrl)) {
        return NextResponse.json(
          { error: 'Please provide a valid GitHub repository URL' },
          { status: 400 }
        )
      }
    }

    // Prepare update data
    const updateData: any = {}
    
    // Network configuration
    if (existingVpcId !== undefined) updateData.existingVpcId = existingVpcId || null
    if (existingSubnetIds !== undefined) updateData.existingSubnetIds = subnetIdsJson
    if (existingClusterArn !== undefined) updateData.existingClusterArn = existingClusterArn || null
    
    // Resource configuration
    if (cpu !== undefined) updateData.cpu = cpu
    if (memory !== undefined) updateData.memory = memory
    if (diskSize !== undefined) updateData.diskSize = diskSize

    // Repository configuration
    if (gitRepoUrl !== undefined) updateData.gitRepoUrl = gitRepoUrl
    if (branch !== undefined) updateData.branch = branch

    // Update project with network and resource configuration
    const updatedProject = await prisma.project.update({
      where: { id: params.id },
      data: updateData,
    })

    return NextResponse.json(updatedProject)
  } catch (error) {
    console.error('Error updating project:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}

export async function DELETE(
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

    // TODO: Clean up AWS resources before deleting
    // For now, just delete the database record

    await prisma.project.delete({
      where: {
        id: params.id,
      },
    })

    return NextResponse.json({ message: 'Project deleted successfully' })
  } catch (error) {
    console.error('Error deleting project:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}