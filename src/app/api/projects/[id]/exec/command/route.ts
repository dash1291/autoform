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

    const { command } = await request.json();
    if (!command || typeof command !== 'string') {
      return NextResponse.json({ error: 'Command is required' }, { status: 400 });
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
    let clusterArn: string;
    let serviceName: string;
    
    try {
      // First try to get from deployment details
      if (latestDeployment.details) {
        const deploymentDetails = JSON.parse(latestDeployment.details);
        clusterArn = deploymentDetails.clusterArn;
      }
      
      // Fallback to project-level cluster ARN for older deployments
      if (!clusterArn && project.ecsClusterArn) {
        clusterArn = project.ecsClusterArn;
      }
      
      serviceName = `${project.name}-service`;
      
      if (!clusterArn) {
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

    // Since ECS Exec only supports interactive mode and we want to keep this simple,
    // we'll create the exec session but note that output cannot be captured
    // without WebSocket streaming
    const execResponse = await ecs.executeCommand({
      cluster: clusterArn,
      task: taskArn,
      container: containerName,
      command: '/bin/sh', // Start a shell session
      interactive: true
    }).promise();

    if (!execResponse.session) {
      return NextResponse.json({ error: 'Failed to create exec session' }, { status: 500 });
    }

    // Return session information
    // Note: The actual command execution would happen through the WebSocket session
    return NextResponse.json({
      success: true,
      command: command,
      sessionId: execResponse.session.sessionId,
      message: `Command "${command}" session created. Note: This creates an interactive session - for full command execution, use the Session Manager console or implement WebSocket streaming.`,
      taskArn: taskArn,
      containerName: containerName,
      sessionUrl: execResponse.session.streamUrl
    });

  } catch (error) {
    console.error('Error executing command:', error);
    return NextResponse.json(
      { error: 'Failed to execute command' },
      { status: 500 }
    );
  }
}