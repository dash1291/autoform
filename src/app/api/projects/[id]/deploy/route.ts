import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'
import { ProjectStatus, DeploymentStatus } from '@/types'
import { DeploymentService } from '@/lib/deployment'

async function startBackgroundDeployment(project: any, deployment: any, commitSha: string) {
  const deploymentService = new DeploymentService();
  
  try {
    // Update deployment status to BUILDING
    await prisma.deployment.update({
      where: { id: deployment.id },
      data: { status: DeploymentStatus.BUILDING }
    });

    await prisma.project.update({
      where: { id: project.id },
      data: { status: ProjectStatus.BUILDING }
    });

    // Start the deployment
    const result = await deploymentService.deployProject({
      projectId: project.id,
      projectName: project.name,
      gitRepoUrl: project.gitRepoUrl,
      branch: project.branch,
      commitSha: commitSha,
    }, deployment.id);

    // Update project and deployment on success
    await prisma.project.update({
      where: { id: project.id },
      data: { 
        status: ProjectStatus.DEPLOYED,
        ecsClusterArn: result.clusterArn,
        ecsServiceArn: result.serviceArn,
        albArn: result.loadBalancerArn,
        domain: result.loadBalancerDns
      }
    });

    await prisma.deployment.update({
      where: { id: deployment.id },
      data: { status: DeploymentStatus.SUCCESS }
    });

    console.log(`✅ Deployment ${deployment.id} completed successfully`);
  } catch (error) {
    console.error(`❌ Deployment ${deployment.id} failed:`, error);
    
    // Update project and deployment on failure
    await prisma.project.update({
      where: { id: project.id },
      data: { status: ProjectStatus.FAILED }
    });

    await prisma.deployment.update({
      where: { id: deployment.id },
      data: { status: DeploymentStatus.FAILED }
    });
  }
}

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

    // Check if project is already deploying
    if (project.status === ProjectStatus.DEPLOYING) {
      return NextResponse.json({ error: 'Project is already deploying' }, { status: 400 })
    }

    // Get the latest commit SHA from the specified branch
    let commitSha: string
    try {
      // Fetch the latest commit from the project's branch
      const user = await prisma.user.findUnique({
        where: { id: session.user.id },
        include: {
          accounts: {
            where: { provider: 'github' }
          }
        }
      })

      if (!user?.accounts?.[0]?.access_token) {
        return NextResponse.json({ error: 'GitHub authentication required' }, { status: 401 })
      }

      // Extract owner and repo from URL
      const match = project.gitRepoUrl.match(/github\.com\/([^\/]+)\/([^\/]+?)(?:\.git)?$/)
      if (!match) {
        return NextResponse.json({ error: 'Invalid GitHub URL format' }, { status: 400 })
      }

      const [, owner, repo] = match

      // Get the latest commit from the branch
      const branchResponse = await fetch(`https://api.github.com/repos/${owner}/${repo}/branches/${project.branch}`, {
        headers: {
          'Authorization': `Bearer ${user.accounts[0].access_token}`,
          'User-Agent': 'Autopilot-PaaS',
          'Accept': 'application/vnd.github.v3+json'
        }
      })

      if (!branchResponse.ok) {
        return NextResponse.json({ 
          error: `Failed to fetch branch '${project.branch}'. Please check if the branch exists.` 
        }, { status: 400 })
      }

      const branchData = await branchResponse.json()
      commitSha = branchData.commit.sha
      console.log(`Using commit SHA ${commitSha} from branch ${project.branch}`)
    } catch (error) {
      console.error('Failed to fetch commit SHA:', error)
      return NextResponse.json({ 
        error: 'Failed to fetch the latest commit from the specified branch' 
      }, { status: 500 })
    }

    // Create deployment record
    const deployment = await prisma.deployment.create({
      data: {
        projectId: project.id,
        status: DeploymentStatus.PENDING,
        imageTag: `${project.name}:${commitSha}`,
        commitSha: commitSha,
      },
    })

    // Update project status
    await prisma.project.update({
      where: {
        id: project.id,
      },
      data: {
        status: ProjectStatus.DEPLOYING,
      },
    })

    // Start actual deployment process in background
    console.log(`Starting deployment for project ${project.name}`)
    
    // Don't await this - let it run in background
    startBackgroundDeployment(project, deployment, commitSha);

    return NextResponse.json({ 
      message: 'Deployment started successfully',
      deployment 
    })
  } catch (error) {
    console.error('Error starting deployment:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}