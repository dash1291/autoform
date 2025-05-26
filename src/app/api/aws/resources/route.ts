import { NextRequest, NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import AWS from 'aws-sdk'

export async function GET(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions)
    if (!session) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const region = process.env.AWS_REGION || 'us-east-1'

    // Configure AWS
    AWS.config.update({
      accessKeyId: process.env.AWS_ACCESS_KEY_ID,
      secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
      region: region
    })

    const ec2 = new AWS.EC2()
    const ecs = new AWS.ECS()

    // Fetch all resources in parallel
    const [vpcsResult, ecsListResult] = await Promise.all([
      ec2.describeVpcs().promise(), // Remove state filter to get all VPCs
      ecs.listClusters().promise()
    ])

    console.log('Raw VPCs:', vpcsResult.Vpcs?.length)
    console.log('Raw ECS clusters:', ecsListResult.clusterArns?.length)

    // Process VPCs
    const vpcs = vpcsResult.Vpcs?.map(vpc => ({
      id: vpc.VpcId,
      name: vpc.Tags?.find(tag => tag.Key === 'Name')?.Value || vpc.VpcId,
      cidrBlock: vpc.CidrBlock,
      isDefault: vpc.IsDefault,
      state: vpc.State
    })) || []

    console.log('Processed VPCs:', vpcs)

    // Fetch subnets for all VPCs in parallel
    const subnetsPromises = vpcs.map(vpc => 
      ec2.describeSubnets({
        Filters: [
          { Name: 'vpc-id', Values: [vpc.id!] },
          { Name: 'state', Values: ['available'] }
        ]
      }).promise()
    )

    const subnetsResults = await Promise.all(subnetsPromises)
    
    // Group subnets by VPC
    const subnetsByVpc: Record<string, any[]> = {}
    subnetsResults.forEach((result, index) => {
      const vpcId = vpcs[index].id!
      subnetsByVpc[vpcId] = result.Subnets?.map(subnet => ({
        id: subnet.SubnetId,
        name: subnet.Tags?.find(tag => tag.Key === 'Name')?.Value || subnet.SubnetId,
        cidrBlock: subnet.CidrBlock,
        availabilityZone: subnet.AvailabilityZone,
        isPublic: subnet.MapPublicIpOnLaunch
      })) || []
    })

    // Process ECS clusters
    let clusters: any[] = []
    if (ecsListResult.clusterArns && ecsListResult.clusterArns.length > 0) {
      const ecsDescribeResult = await ecs.describeClusters({
        clusters: ecsListResult.clusterArns
      }).promise()

      console.log('Raw ECS cluster details:', ecsDescribeResult.clusters)

      clusters = ecsDescribeResult.clusters?.map(cluster => ({
        arn: cluster.clusterArn,
        name: cluster.clusterName,
        status: cluster.status,
        runningTasksCount: cluster.runningTasksCount,
        pendingTasksCount: cluster.pendingTasksCount,
        activeServicesCount: cluster.activeServicesCount
      })) || [] // Remove ACTIVE filter to see all clusters

      console.log('Processed clusters:', clusters)
    }

    return NextResponse.json({
      vpcs,
      subnetsByVpc,
      clusters,
      region
    })
  } catch (error) {
    console.error('Error fetching AWS resources:', error)
    return NextResponse.json(
      { error: 'Failed to fetch AWS resources' },
      { status: 500 }
    )
  }
}