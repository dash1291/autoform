import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { authOptions } from '@/lib/auth';
import { prisma } from '@/lib/prisma';
import * as AWS from 'aws-sdk';

// Initialize AWS ECS client
const ecs = new AWS.ECS({ region: process.env.AWS_REGION || 'us-east-1' });

export async function POST(request: NextRequest, { params }: { params: { id: string } }) {
  try {
    const session = await getServerSession(authOptions);
    if (!session?.user?.email) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const projectId = params.id;

    // Get project and verify ownership
    const project = await prisma.project.findFirst({
      where: {
        id: projectId,
        user: {
          email: session.user.email
        }
      },
      include: {
        deployments: {
          where: { status: 'SUCCESS' },
          orderBy: { createdAt: 'desc' },
          take: 1
        }
      }
    });

    if (!project) {
      return NextResponse.json({ error: 'Project not found' }, { status: 404 });
    }

    if (project.deployments.length === 0) {
      return NextResponse.json({ error: 'No active deployment found' }, { status: 404 });
    }

    const latestDeployment = project.deployments[0];
    
    // Parse deployment details to get cluster and service info
    const serviceName = `${project.name}-service`;
    let clusterArn: string;
    
    try {
      // Get cluster ARN from deployment details or project
      if (latestDeployment.details) {
        const deploymentDetails = JSON.parse(latestDeployment.details);
        clusterArn = deploymentDetails.clusterArn;
      } else if (project.ecsClusterArn) {
        clusterArn = project.ecsClusterArn;
      } else {
        throw new Error('Cluster ARN not found in deployment details or project');
      }
    } catch (error) {
      return NextResponse.json({ error: 'Invalid deployment details' }, { status: 400 });
    }

    // Get running tasks for the service
    const services = await ecs.describeServices({
      cluster: clusterArn,
      services: [serviceName]
    }).promise();

    if (!services.services || services.services.length === 0) {
      return NextResponse.json({ error: 'Service not found' }, { status: 404 });
    }

    const service = services.services[0];
    if (service.runningCount === 0) {
      return NextResponse.json({ error: 'No running tasks found' }, { status: 404 });
    }

    // Get tasks for the service
    const tasks = await ecs.listTasks({
      cluster: clusterArn,
      serviceName: serviceName
    }).promise();

    if (!tasks.taskArns || tasks.taskArns.length === 0) {
      return NextResponse.json({ error: 'No tasks found' }, { status: 404 });
    }

    // Get the first running task
    const taskArn = tasks.taskArns[0];
    const containerName = project.name;

    // Return connection info for command execution
    return NextResponse.json({
      success: true,
      message: 'Container access available',
      clusterArn,
      taskArn,
      containerName
    });

  } catch (error) {
    console.error('Error creating exec session:', error);
    return NextResponse.json(
      { error: 'Failed to create exec session' },
      { status: 500 }
    );
  }
}

export async function GET(request: NextRequest, { params }: { params: { id: string } }) {
  try {
    const session = await getServerSession(authOptions);
    if (!session?.user?.email) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const projectId = params.id;

    // Get project and verify ownership
    const project = await prisma.project.findFirst({
      where: {
        id: projectId,
        user: {
          email: session.user.email
        }
      },
      include: {
        deployments: {
          where: { status: 'SUCCESS' },
          orderBy: { createdAt: 'desc' },
          take: 1
        }
      }
    });

    if (!project) {
      return NextResponse.json({ error: 'Project not found' }, { status: 404 });
    }

    if (project.deployments.length === 0) {
      return NextResponse.json({ 
        available: false, 
        reason: 'No active deployment found' 
      });
    }

    const latestDeployment = project.deployments[0];
    
    // Parse deployment details to get cluster and service info
    const serviceName = `${project.name}-service`;
    let clusterArn: string;
    
    try {
      // Get cluster ARN from deployment details or project
      if (latestDeployment.details) {
        const deploymentDetails = JSON.parse(latestDeployment.details);
        clusterArn = deploymentDetails.clusterArn;
      } else if (project.ecsClusterArn) {
        clusterArn = project.ecsClusterArn;
      } else {
        throw new Error('Cluster ARN not found in deployment details or project');
      }
    } catch (error) {
      return NextResponse.json({ 
        available: false, 
        reason: 'Invalid deployment details' 
      });
    }

    // Check service status
    const services = await ecs.describeServices({
      cluster: clusterArn,
      services: [serviceName]
    }).promise();

    if (!services.services || services.services.length === 0) {
      return NextResponse.json({ 
        available: false, 
        reason: 'Service not found' 
      });
    }

    const service = services.services[0];
    const isAvailable = (service.runningCount ?? 0) > 0 && service.status === 'ACTIVE';

    let taskArn = null;
    if (isAvailable) {
      // Get running tasks for the service
      const tasks = await ecs.listTasks({
        cluster: clusterArn,
        serviceName: serviceName
      }).promise();

      if (tasks.taskArns && tasks.taskArns.length > 0) {
        taskArn = tasks.taskArns[0];
      }
    }

    return NextResponse.json({
      available: isAvailable,
      runningCount: service.runningCount,
      desiredCount: service.desiredCount,
      status: service.status,
      clusterArn: isAvailable ? clusterArn : undefined,
      taskArn: taskArn,
      containerName: isAvailable ? project.name : undefined
    });

  } catch (error) {
    console.error('Error checking exec availability:', error);
    return NextResponse.json({ 
      available: false, 
      reason: 'Error checking service status' 
    });
  }
}