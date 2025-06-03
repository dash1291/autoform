import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'
import { ProjectStatus } from '@/types'

export async function GET() {
  try {
    const session = await getServerSession(authOptions)
    
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const projects = await prisma.project.findMany({
      where: {
        userId: session.user.id,
      },
      orderBy: {
        createdAt: 'desc',
      },
    })

    return NextResponse.json(projects)
  } catch (error) {
    console.error('Error fetching projects:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}

export async function POST(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions)
    
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const body = await request.json()
    const { name, gitRepoUrl, branch = 'main', cpu = 256, memory = 512, diskSize = 21 } = body

    if (!name || !gitRepoUrl) {
      return NextResponse.json(
        { error: 'Name and Git repository URL are required' },
        { status: 400 }
      )
    }

    // Validate Git URL format
    const gitUrlRegex = /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+(?:\.git)?$/
    if (!gitUrlRegex.test(gitRepoUrl)) {
      return NextResponse.json(
        { error: 'Please provide a valid GitHub repository URL' },
        { status: 400 }
      )
    }

    // Check if project name already exists for this user
    const existingProject = await prisma.project.findFirst({
      where: {
        userId: session.user.id,
        name: name,
      },
    })

    if (existingProject) {
      return NextResponse.json(
        { error: 'A project with this name already exists' },
        { status: 400 }
      )
    }

    // Validate resource configurations
    if (cpu < 256 || cpu > 4096) {
      return NextResponse.json(
        { error: 'CPU must be between 256 and 4096' },
        { status: 400 }
      )
    }
    
    if (memory < 512 || memory > 30720) {
      return NextResponse.json(
        { error: 'Memory must be between 512 and 30720 MB' },
        { status: 400 }
      )
    }
    
    if (diskSize < 21 || diskSize > 200) {
      return NextResponse.json(
        { error: 'Disk size must be between 21 and 200 GB' },
        { status: 400 }
      )
    }

    // Create the project
    const project = await prisma.project.create({
      data: {
        name,
        gitRepoUrl,
        branch,
        userId: session.user.id,
        status: ProjectStatus.CREATED,
        cpu,
        memory,
        diskSize,
      },
    })

    // TODO: Trigger deployment process here
    // For now, we'll just create the project record

    return NextResponse.json(project, { status: 201 })
  } catch (error) {
    console.error('Error creating project:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}