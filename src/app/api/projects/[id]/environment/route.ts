import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'
import AWS from 'aws-sdk'

// GET - Fetch environment variables for a project
export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const session = await getServerSession(authOptions)
    
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const projectId = params.id

    // Verify user owns the project
    const project = await prisma.project.findFirst({
      where: {
        id: projectId,
        userId: session.user.id
      }
    })

    if (!project) {
      return NextResponse.json({ error: 'Project not found' }, { status: 404 })
    }

    // Fetch environment variables
    const envVars = await prisma.environmentVariable.findMany({
      where: {
        projectId
      },
      orderBy: {
        key: 'asc'
      }
    })

    // For secrets, don't return the actual values
    const sanitizedEnvVars = envVars.map(envVar => ({
      ...envVar,
      value: envVar.isSecret ? undefined : envVar.value
    }))

    return NextResponse.json(sanitizedEnvVars)

  } catch (error) {
    console.error('Error fetching environment variables:', error)
    return NextResponse.json(
      { error: 'Failed to fetch environment variables' },
      { status: 500 }
    )
  }
}

// POST - Create or update environment variable
export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const session = await getServerSession(authOptions)
    
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const projectId = params.id
    const { key, value, isSecret } = await request.json()

    if (!key || (!value && !isSecret)) {
      return NextResponse.json(
        { error: 'Key and value are required' },
        { status: 400 }
      )
    }

    // Verify user owns the project
    const project = await prisma.project.findFirst({
      where: {
        id: projectId,
        userId: session.user.id
      }
    })

    if (!project) {
      return NextResponse.json({ error: 'Project not found' }, { status: 404 })
    }

    let secretKey = undefined
    let storedValue = value

    if (isSecret) {
      // Store in AWS Secrets Manager
      const region = process.env.AWS_REGION || 'us-east-1'
      AWS.config.update({ region })
      const secretsManager = new AWS.SecretsManager({ region })

      const secretName = `${project.name}/${key}`
      secretKey = secretName

      try {
        // Try to update existing secret
        await secretsManager.updateSecret({
          SecretId: secretName,
          SecretString: value
        }).promise()
      } catch (error: any) {
        if (error.code === 'ResourceNotFoundException') {
          // Create new secret
          await secretsManager.createSecret({
            Name: secretName,
            SecretString: value,
            Description: `Secret for ${project.name} project`
          }).promise()
        } else {
          throw error
        }
      }

      // Don't store the actual value in database for secrets
      storedValue = undefined
    }

    // Upsert environment variable
    const envVar = await prisma.environmentVariable.upsert({
      where: {
        projectId_key: {
          projectId,
          key
        }
      },
      update: {
        value: storedValue,
        isSecret,
        secretKey
      },
      create: {
        projectId,
        key,
        value: storedValue,
        isSecret,
        secretKey
      }
    })

    // Return sanitized response
    return NextResponse.json({
      ...envVar,
      value: envVar.isSecret ? undefined : envVar.value
    })

  } catch (error) {
    console.error('Error creating/updating environment variable:', error)
    return NextResponse.json(
      { error: 'Failed to save environment variable' },
      { status: 500 }
    )
  }
}

// DELETE - Delete environment variable
export async function DELETE(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const session = await getServerSession(authOptions)
    
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const projectId = params.id
    const url = new URL(request.url)
    const key = url.searchParams.get('key')

    if (!key) {
      return NextResponse.json(
        { error: 'Key parameter is required' },
        { status: 400 }
      )
    }

    // Verify user owns the project
    const project = await prisma.project.findFirst({
      where: {
        id: projectId,
        userId: session.user.id
      }
    })

    if (!project) {
      return NextResponse.json({ error: 'Project not found' }, { status: 404 })
    }

    // Find the environment variable
    const envVar = await prisma.environmentVariable.findUnique({
      where: {
        projectId_key: {
          projectId,
          key
        }
      }
    })

    if (!envVar) {
      return NextResponse.json({ error: 'Environment variable not found' }, { status: 404 })
    }

    // If it's a secret, delete from AWS Secrets Manager
    if (envVar.isSecret && envVar.secretKey) {
      const region = process.env.AWS_REGION || 'us-east-1'
      AWS.config.update({ region })
      const secretsManager = new AWS.SecretsManager({ region })

      try {
        await secretsManager.deleteSecret({
          SecretId: envVar.secretKey,
          ForceDeleteWithoutRecovery: true
        }).promise()
      } catch (error) {
        console.error('Error deleting secret from AWS:', error)
        // Continue with database deletion even if AWS deletion fails
      }
    }

    // Delete from database
    await prisma.environmentVariable.delete({
      where: {
        projectId_key: {
          projectId,
          key
        }
      }
    })

    return NextResponse.json({ success: true })

  } catch (error) {
    console.error('Error deleting environment variable:', error)
    return NextResponse.json(
      { error: 'Failed to delete environment variable' },
      { status: 500 }
    )
  }
}