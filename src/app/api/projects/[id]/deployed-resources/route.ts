import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { prisma } from '@/lib/prisma'
import AWS from 'aws-sdk'

export async function GET(request: NextRequest, { params }: { params: { id: string } }) {
  try {
    const session = await getServerSession(authOptions)
    if (!session) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const project = await prisma.project.findUnique({
      where: { id: params.id },
      select: {
        userId: true,
        ecsServiceArn: true,
        existingVpcId: true,
        existingSubnetIds: true,
        existingClusterArn: true,
        name: true
      }
    })

    if (!project || project.userId !== session.user.id) {
      return NextResponse.json({ error: 'Project not found' }, { status: 404 })
    }

    const region = process.env.AWS_REGION || 'us-east-1'
    AWS.config.update({
      accessKeyId: process.env.AWS_ACCESS_KEY_ID,
      secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
      region: region
    })

    const ec2 = new AWS.EC2()
    const ecs = new AWS.ECS()

    let actualVpcId = project.existingVpcId
    let actualSubnetIds: string[] = []
    let actualClusterArn = project.existingClusterArn

    // If using existing resources, we already have the IDs
    if (project.existingVpcId) {
      actualVpcId = project.existingVpcId
    }

    if (project.existingSubnetIds) {
      try {
        actualSubnetIds = JSON.parse(project.existingSubnetIds)
      } catch (error) {
        console.error('Failed to parse existing subnet IDs:', error)
      }
    }

    // If no existing resources configured, try to find the auto-created ones
    if (!actualVpcId && project.ecsServiceArn) {
      try {
        // Find VPC by project name tag
        const vpcs = await ec2.describeVpcs({
          Filters: [
            { Name: 'tag:Name', Values: [`${project.name}-vpc`] },
            { Name: 'state', Values: ['available'] }
          ]
        }).promise()

        if (vpcs.Vpcs && vpcs.Vpcs.length > 0) {
          actualVpcId = vpcs.Vpcs[0].VpcId
        }
      } catch (error) {
        console.error('Failed to find auto-created VPC:', error)
      }
    }

    // If no existing subnets configured, try to find the auto-created ones
    if (actualSubnetIds.length === 0 && project.ecsServiceArn) {
      try {
        // Get subnets from ECS service
        const services = await ecs.describeServices({
          cluster: actualClusterArn || `${project.name}-cluster`,
          services: [project.ecsServiceArn]
        }).promise()

        if (services.services && services.services.length > 0) {
          const service = services.services[0]
          const subnets = service.networkConfiguration?.awsvpcConfiguration?.subnets
          if (subnets) {
            actualSubnetIds = subnets
          }
        }
      } catch (error) {
        console.error('Failed to get subnets from ECS service:', error)
        
        // Fallback: find subnets by project name tag
        try {
          const subnets = await ec2.describeSubnets({
            Filters: [
              { Name: 'tag:Name', Values: [`${project.name}-public-subnet-1`, `${project.name}-public-subnet-2`] },
              { Name: 'state', Values: ['available'] }
            ]
          }).promise()

          if (subnets.Subnets) {
            actualSubnetIds = subnets.Subnets.map(subnet => subnet.SubnetId!).filter(Boolean)
          }
        } catch (error) {
          console.error('Failed to find auto-created subnets:', error)
        }
      }
    }

    // Get VPC details if we have the ID
    let vpcDetails = null
    if (actualVpcId) {
      try {
        const vpcResult = await ec2.describeVpcs({
          VpcIds: [actualVpcId]
        }).promise()

        if (vpcResult.Vpcs && vpcResult.Vpcs.length > 0) {
          const vpc = vpcResult.Vpcs[0]
          vpcDetails = {
            id: vpc.VpcId,
            name: vpc.Tags?.find(tag => tag.Key === 'Name')?.Value || vpc.VpcId,
            cidrBlock: vpc.CidrBlock,
            isDefault: vpc.IsDefault
          }
        }
      } catch (error) {
        console.error('Failed to get VPC details:', error)
      }
    }

    // Get subnet details if we have the IDs
    let subnetDetails: any[] = []
    if (actualSubnetIds.length > 0) {
      try {
        const subnetResult = await ec2.describeSubnets({
          SubnetIds: actualSubnetIds
        }).promise()

        if (subnetResult.Subnets) {
          subnetDetails = subnetResult.Subnets.map(subnet => ({
            id: subnet.SubnetId,
            name: subnet.Tags?.find(tag => tag.Key === 'Name')?.Value || subnet.SubnetId,
            cidrBlock: subnet.CidrBlock,
            availabilityZone: subnet.AvailabilityZone,
            isPublic: subnet.MapPublicIpOnLaunch
          }))
        }
      } catch (error) {
        console.error('Failed to get subnet details:', error)
      }
    }

    // Get cluster details
    let clusterDetails = null
    
    // Try to find cluster - either existing one or auto-created one
    const clusterName = actualClusterArn || `${project.name}-cluster`
    
    try {
      console.log('Looking for cluster:', clusterName)
      const clusterResult = await ecs.describeClusters({
        clusters: [clusterName]
      }).promise()

      console.log('Cluster lookup result:', clusterResult)

      if (clusterResult.clusters && clusterResult.clusters.length > 0) {
        const cluster = clusterResult.clusters[0]
        
        // Only include if cluster is active/exists
        if (cluster.status === 'ACTIVE') {
          clusterDetails = {
            arn: cluster.clusterArn,
            name: cluster.clusterName,
            status: cluster.status,
            runningTasksCount: cluster.runningTasksCount,
            activeServicesCount: cluster.activeServicesCount
          }
          
          // Update actualClusterArn for consistency
          actualClusterArn = cluster.clusterArn
        }
      }
    } catch (error) {
      console.error('Failed to get cluster details for:', clusterName, error)
    }

    return NextResponse.json({
      vpc: vpcDetails,
      subnets: subnetDetails,
      cluster: clusterDetails,
      region
    })
  } catch (error) {
    console.error('Error fetching deployed resources:', error)
    return NextResponse.json(
      { error: 'Failed to fetch deployed resources' },
      { status: 500 }
    )
  }
}