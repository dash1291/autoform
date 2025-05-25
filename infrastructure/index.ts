import * as AWS from 'aws-sdk';

export interface EnvironmentVariable {
  key: string;
  value?: string;
  isSecret: boolean;
  secretKey?: string;
}

export interface ECSInfrastructureArgs {
  projectName: string;
  imageUri: string;
  containerPort?: number;
  region?: string;
  existingVpcId?: string;
  existingSubnetIds?: string[];
  existingClusterArn?: string;
  environmentVariables?: EnvironmentVariable[];
}

export interface ECSInfrastructureOutput {
  clusterArn: string;
  serviceArn: string;
  loadBalancerArn: string;
  loadBalancerDns: string;
}

export class ECSInfrastructure {
  private ec2: AWS.EC2;
  private ecs: AWS.ECS;
  private elbv2: AWS.ELBv2;
  private iam: AWS.IAM;
  private logs: AWS.CloudWatchLogs;
  private projectName: string;
  private imageUri: string;
  private containerPort: number;
  private args: ECSInfrastructureArgs;
  private region: string;

  constructor(args: ECSInfrastructureArgs) {
    this.region = args.region || 'us-east-1';
    AWS.config.update({ region: this.region });

    this.ec2 = new AWS.EC2();
    this.ecs = new AWS.ECS();
    this.elbv2 = new AWS.ELBv2();
    this.iam = new AWS.IAM();
    this.logs = new AWS.CloudWatchLogs();
    this.projectName = args.projectName;
    this.imageUri = args.imageUri;
    this.containerPort = args.containerPort || 3000;
    this.args = args;
  }

  private async findExistingResources() {
    try {
      // Find existing VPC
      const vpcs = await this.ec2.describeVpcs({
        Filters: [
          { Name: 'tag:Name', Values: [`${this.projectName}-vpc`] },
          { Name: 'state', Values: ['available'] }
        ]
      }).promise();

      // Find existing subnets
      const subnets = await this.ec2.describeSubnets({
        Filters: [
          { Name: 'tag:Name', Values: [`${this.projectName}-public-subnet-1`, `${this.projectName}-public-subnet-2`] },
          { Name: 'state', Values: ['available'] }
        ]
      }).promise();

      // Find existing ECS cluster
      let cluster = null;
      try {
        const clusters = await this.ecs.describeClusters({
          clusters: [`${this.projectName}-cluster`]
        }).promise();
        if (clusters.clusters && clusters.clusters.length > 0 && clusters.clusters[0].status === 'ACTIVE') {
          cluster = clusters.clusters[0];
        }
      } catch (error) {
        // Cluster doesn't exist
      }

      // Find existing load balancer
      let loadBalancer = null;
      try {
        const lbs = await this.elbv2.describeLoadBalancers({
          Names: [`${this.projectName}-alb`]
        }).promise();
        if (lbs.LoadBalancers && lbs.LoadBalancers.length > 0) {
          loadBalancer = lbs.LoadBalancers[0];
        }
      } catch (error) {
        // Load balancer doesn't exist
      }

      return {
        vpc: vpcs.Vpcs && vpcs.Vpcs.length > 0 ? vpcs.Vpcs[0] : null,
        subnets: subnets.Subnets || [],
        cluster,
        loadBalancer
      };
    } catch (error) {
      console.error('Error finding existing resources:', error);
      return { vpc: null, subnets: [], cluster: null, loadBalancer: null };
    }
  }

  async createOrUpdateInfrastructure(): Promise<ECSInfrastructureOutput> {
    try {
      // Find existing resources first
      const existing = await this.findExistingResources();
      
      let vpcId: string;
      let subnetIds: string[];
      let clusterArn: string | undefined;

      // VPC - Use existing or create new
      if (this.args.existingVpcId) {
        vpcId = this.args.existingVpcId;
        console.log(`Using existing VPC: ${vpcId}`);
      } else if (existing.vpc) {
        vpcId = existing.vpc.VpcId!;
        console.log(`Found existing VPC for project: ${vpcId}`);
      } else {
        const vpc = await this.createOrUpdateVPC();
        vpcId = vpc.VpcId!;
        console.log(`Created new VPC: ${vpcId}`);
      }
      
      // Subnets - Use existing or create new
      if (this.args.existingSubnetIds) {
        subnetIds = this.args.existingSubnetIds;
        console.log(`Using provided subnet IDs: ${subnetIds.join(', ')}`);
      } else if (existing.subnets.length >= 2) {
        subnetIds = existing.subnets.map((s: any) => s.SubnetId!);
        console.log(`Found existing subnets: ${subnetIds.join(', ')}`);
      } else {
        subnetIds = await this.createOrUpdateSubnets(vpcId);
        console.log(`Created new subnets: ${subnetIds.join(', ')}`);
      }

      // Internet Gateway and routes - Only if creating new VPC
      if (!this.args.existingVpcId && !existing.vpc) {
        await this.createOrUpdateNetworking(vpcId, subnetIds);
      }
      
      // Security groups - Always ensure they exist with correct rules
      const securityGroups = await this.createOrUpdateSecurityGroups(vpcId);
      
      // IAM roles - Always ensure they exist
      const roles = await this.createOrUpdateIAMRoles();
      
      // CloudWatch log group - Always ensure it exists
      await this.createOrUpdateLogGroup();
      
      // ECS Cluster - Use existing or create new
      if (this.args.existingClusterArn) {
        clusterArn = this.args.existingClusterArn;
        console.log(`Using provided cluster: ${clusterArn}`);
      } else if (existing.cluster) {
        clusterArn = existing.cluster.clusterArn!;
        console.log(`Found existing cluster: ${clusterArn}`);
      } else {
        const clusterResult = await this.createOrUpdateECSCluster();
        clusterArn = clusterResult.cluster?.clusterArn!;
        console.log(`Created new cluster: ${clusterArn}`);
      }
      
      // Task definition - Always create new version if image changed
      // Verify log group exists before creating task definition
      const logGroupName = `/ecs/${this.projectName}`;
      try {
        const logGroups = await this.logs.describeLogGroups({ 
          logGroupNamePrefix: logGroupName 
        }).promise();
        
        const logGroupExists = logGroups.logGroups?.some(lg => lg.logGroupName === logGroupName);
        if (!logGroupExists) {
          throw new Error(`Log group ${logGroupName} does not exist`);
        }
        console.log(`✅ Verified log group exists: ${logGroupName}`);
      } catch (error) {
        console.error(`Log group verification failed: ${error}`);
        throw new Error(`Log group ${logGroupName} is required but does not exist. Infrastructure setup may have failed.`);
      }
      
      const taskDefinition = await this.createTaskDefinition(roles);
      
      // Load balancer - Use existing or create new
      let loadBalancer = existing.loadBalancer;
      if (!loadBalancer) {
        const lbResponse = await this.createLoadBalancer(subnetIds, securityGroups.albSecurityGroupId);
        loadBalancer = lbResponse.LoadBalancers![0];
        console.log(`Created new load balancer: ${loadBalancer.LoadBalancerArn}`);
      }
      
      // Target group - Use existing or create new
      const tgResponse = await this.createTargetGroup(vpcId);
      const targetGroup = tgResponse.TargetGroups![0];
      console.log(`Created target group: ${targetGroup.TargetGroupArn}`);
      
      // Listener - Ensure it exists
      await this.createListener(loadBalancer.LoadBalancerArn!, targetGroup.TargetGroupArn!);
      
      // ECS service - Update existing or create new
      const serviceResponse = await this.createOrUpdateECSService(
        clusterArn,
        taskDefinition.taskDefinition!.taskDefinitionArn!,
        subnetIds,
        securityGroups.ecsSecurityGroupId,
        targetGroup.TargetGroupArn!
      );
      const service = serviceResponse.service!;
      console.log(`ECS service ready: ${service.serviceArn}`);

      return {
        clusterArn,
        serviceArn: service.serviceArn!,
        loadBalancerArn: loadBalancer.LoadBalancerArn!,
        loadBalancerDns: loadBalancer.DNSName!,
      };
    } catch (error) {
      console.error('Error creating/updating infrastructure:', error);
      throw error;
    }
  }

  private async createOrUpdateVPC() {
    // Check if VPC already exists
    try {
      const vpcs = await this.ec2.describeVpcs({
        Filters: [
          { Name: 'tag:Name', Values: [`${this.projectName}-vpc`] },
          { Name: 'state', Values: ['available'] }
        ]
      }).promise();

      if (vpcs.Vpcs && vpcs.Vpcs.length > 0) {
        console.log(`Found existing VPC: ${vpcs.Vpcs[0].VpcId}`);
        return vpcs.Vpcs[0];
      }
    } catch (error) {
      console.log('No existing VPC found, creating new one');
    }

    return this.createVPC();
  }

  private async createVPC() {
    const params = {
      CidrBlock: '10.0.0.0/16',
      TagSpecifications: [{
        ResourceType: 'vpc',
        Tags: [{ Key: 'Name', Value: `${this.projectName}-vpc` }]
      }]
    };

    const result = await this.ec2.createVpc(params).promise();
    
    await this.ec2.modifyVpcAttribute({
      VpcId: result.Vpc!.VpcId!,
      EnableDnsHostnames: { Value: true }
    }).promise();

    await this.ec2.modifyVpcAttribute({
      VpcId: result.Vpc!.VpcId!,
      EnableDnsSupport: { Value: true }
    }).promise();

    return result.Vpc!;
  }

  private async createOrUpdateSubnets(vpcId: string): Promise<string[]> {
    // Check if subnets already exist
    try {
      const subnets = await this.ec2.describeSubnets({
        Filters: [
          { Name: 'vpc-id', Values: [vpcId] },
          { Name: 'tag:Name', Values: [`${this.projectName}-public-subnet-1`, `${this.projectName}-public-subnet-2`] },
          { Name: 'state', Values: ['available'] }
        ]
      }).promise();

      if (subnets.Subnets && subnets.Subnets.length >= 2) {
        const subnetIds = subnets.Subnets.map((s: any) => s.SubnetId!).sort();
        console.log(`Found existing subnets: ${subnetIds.join(', ')}`);
        return subnetIds;
      }
    } catch (error) {
      console.log('No existing subnets found, creating new ones');
    }

    return this.createSubnets(vpcId);
  }

  private async createSubnets(vpcId: string) {
    const subnet1 = await this.ec2.createSubnet({
      VpcId: vpcId,
      CidrBlock: '10.0.1.0/24',
      AvailabilityZone: `${this.region}a`,
      TagSpecifications: [{
        ResourceType: 'subnet',
        Tags: [{ Key: 'Name', Value: `${this.projectName}-public-subnet-1` }]
      }]
    }).promise();

    const subnet2 = await this.ec2.createSubnet({
      VpcId: vpcId,
      CidrBlock: '10.0.2.0/24',
      AvailabilityZone: `${this.region}b`,
      TagSpecifications: [{
        ResourceType: 'subnet',
        Tags: [{ Key: 'Name', Value: `${this.projectName}-public-subnet-2` }]
      }]
    }).promise();

    await this.ec2.modifySubnetAttribute({
      SubnetId: subnet1.Subnet!.SubnetId!,
      MapPublicIpOnLaunch: { Value: true }
    }).promise();

    await this.ec2.modifySubnetAttribute({
      SubnetId: subnet2.Subnet!.SubnetId!,
      MapPublicIpOnLaunch: { Value: true }
    }).promise();

    return [subnet1.Subnet!.SubnetId!, subnet2.Subnet!.SubnetId!];
  }

  private async createInternetGateway(vpcId: string) {
    const igw = await this.ec2.createInternetGateway({
      TagSpecifications: [{
        ResourceType: 'internet-gateway',
        Tags: [{ Key: 'Name', Value: `${this.projectName}-igw` }]
      }]
    }).promise();

    await this.ec2.attachInternetGateway({
      VpcId: vpcId,
      InternetGatewayId: igw.InternetGateway!.InternetGatewayId!
    }).promise();

    return igw.InternetGateway!;
  }

  private async createRouteTable(vpcId: string, igwId: string, subnets: string[]) {
    const routeTable = await this.ec2.createRouteTable({
      VpcId: vpcId,
      TagSpecifications: [{
        ResourceType: 'route-table',
        Tags: [{ Key: 'Name', Value: `${this.projectName}-public-rt` }]
      }]
    }).promise();

    await this.ec2.createRoute({
      RouteTableId: routeTable.RouteTable!.RouteTableId!,
      DestinationCidrBlock: '0.0.0.0/0',
      GatewayId: igwId
    }).promise();

    for (const subnetId of subnets) {
      await this.ec2.associateRouteTable({
        RouteTableId: routeTable.RouteTable!.RouteTableId!,
        SubnetId: subnetId
      }).promise();
    }
  }

  private async createOrUpdateNetworking(vpcId: string, subnetIds: string[]) {
    const igw = await this.createOrUpdateInternetGateway(vpcId);
    await this.createOrUpdateRouteTable(vpcId, igw.InternetGatewayId!, subnetIds);
  }

  private async createOrUpdateInternetGateway(vpcId: string) {
    // Check if IGW already exists
    try {
      const igws = await this.ec2.describeInternetGateways({
        Filters: [
          { Name: 'attachment.vpc-id', Values: [vpcId] },
          { Name: 'tag:Name', Values: [`${this.projectName}-igw`] }
        ]
      }).promise();

      if (igws.InternetGateways && igws.InternetGateways.length > 0) {
        console.log(`Found existing IGW: ${igws.InternetGateways[0].InternetGatewayId}`);
        return igws.InternetGateways[0];
      }
    } catch (error) {
      console.log('No existing IGW found, creating new one');
    }

    return this.createInternetGateway(vpcId);
  }

  private async createOrUpdateRouteTable(vpcId: string, igwId: string, subnets: string[]) {
    // Check if route table already exists
    try {
      const routeTables = await this.ec2.describeRouteTables({
        Filters: [
          { Name: 'vpc-id', Values: [vpcId] },
          { Name: 'tag:Name', Values: [`${this.projectName}-public-rt`] }
        ]
      }).promise();

      if (routeTables.RouteTables && routeTables.RouteTables.length > 0) {
        const routeTable = routeTables.RouteTables[0];
        console.log(`Found existing route table: ${routeTable.RouteTableId}`);
        
        // Ensure IGW route exists
        const hasIgwRoute = routeTable.Routes?.some(r => 
          r.DestinationCidrBlock === '0.0.0.0/0' && r.GatewayId === igwId
        );
        
        if (!hasIgwRoute) {
          await this.ec2.createRoute({
            RouteTableId: routeTable.RouteTableId!,
            DestinationCidrBlock: '0.0.0.0/0',
            GatewayId: igwId
          }).promise();
          console.log('Added IGW route to existing route table');
        }
        
        // Ensure subnet associations
        for (const subnetId of subnets) {
          const hasAssociation = routeTable.Associations?.some(a => a.SubnetId === subnetId);
          if (!hasAssociation) {
            await this.ec2.associateRouteTable({
              RouteTableId: routeTable.RouteTableId!,
              SubnetId: subnetId
            }).promise();
            console.log(`Associated subnet ${subnetId} with route table`);
          }
        }
        return;
      }
    } catch (error) {
      console.log('No existing route table found, creating new one');
    }

    return this.createRouteTable(vpcId, igwId, subnets);
  }

  private async createOrUpdateSecurityGroups(vpcId: string) {
    const albSg = await this.createOrUpdateSecurityGroup(
      `${this.projectName}-alb-sg`,
      'ALB Security Group',
      vpcId,
      [
        { IpProtocol: 'tcp', FromPort: 80, ToPort: 80, IpRanges: [{ CidrIp: '0.0.0.0/0' }] },
        { IpProtocol: 'tcp', FromPort: 443, ToPort: 443, IpRanges: [{ CidrIp: '0.0.0.0/0' }] }
      ]
    );

    const ecsSg = await this.createOrUpdateSecurityGroup(
      `${this.projectName}-ecs-sg`,
      'ECS Security Group',
      vpcId,
      [
        { IpProtocol: 'tcp', FromPort: this.containerPort, ToPort: this.containerPort, UserIdGroupPairs: [{ GroupId: albSg }] }
      ]
    );

    return {
      albSecurityGroupId: albSg,
      ecsSecurityGroupId: ecsSg
    };
  }

  private async createOrUpdateSecurityGroup(name: string, description: string, vpcId: string, rules: any[]) {
    // Check if security group already exists
    try {
      const sgs = await this.ec2.describeSecurityGroups({
        Filters: [
          { Name: 'group-name', Values: [name] },
          { Name: 'vpc-id', Values: [vpcId] }
        ]
      }).promise();

      if (sgs.SecurityGroups && sgs.SecurityGroups.length > 0) {
        const sg = sgs.SecurityGroups[0];
        console.log(`Found existing security group: ${sg.GroupId}`);
        
        // Update rules if needed
        await this.updateSecurityGroupRules(sg.GroupId!, rules);
        return sg.GroupId!;
      }
    } catch (error) {
      console.log(`No existing security group found for ${name}, creating new one`);
    }

    // Create new security group
    const sg = await this.ec2.createSecurityGroup({
      GroupName: name,
      Description: description,
      VpcId: vpcId,
      TagSpecifications: [{
        ResourceType: 'security-group',
        Tags: [{ Key: 'Name', Value: name }]
      }]
    }).promise();

    // Add rules
    if (rules.length > 0) {
      await this.ec2.authorizeSecurityGroupIngress({
        GroupId: sg.GroupId!,
        IpPermissions: rules
      }).promise();
    }

    console.log(`Created new security group: ${sg.GroupId}`);
    return sg.GroupId!;
  }

  private async updateSecurityGroupRules(groupId: string, newRules: any[]) {
    // For simplicity, we'll assume rules are correct if SG exists
    // In production, you might want to compare and update rules
    console.log(`Security group ${groupId} rules assumed to be correct`);
  }

  private async createSecurityGroups(vpcId: string) {
    const albSg = await this.ec2.createSecurityGroup({
      GroupName: `${this.projectName}-alb-sg`,
      Description: 'ALB Security Group',
      VpcId: vpcId,
      TagSpecifications: [{
        ResourceType: 'security-group',
        Tags: [{ Key: 'Name', Value: `${this.projectName}-alb-sg` }]
      }]
    }).promise();

    await this.ec2.authorizeSecurityGroupIngress({
      GroupId: albSg.GroupId!,
      IpPermissions: [{
        IpProtocol: 'tcp',
        FromPort: 80,
        ToPort: 80,
        IpRanges: [{ CidrIp: '0.0.0.0/0' }]
      }, {
        IpProtocol: 'tcp',
        FromPort: 443,
        ToPort: 443,
        IpRanges: [{ CidrIp: '0.0.0.0/0' }]
      }]
    }).promise();

    const ecsSg = await this.ec2.createSecurityGroup({
      GroupName: `${this.projectName}-ecs-sg`,
      Description: 'ECS Security Group',
      VpcId: vpcId,
      TagSpecifications: [{
        ResourceType: 'security-group',
        Tags: [{ Key: 'Name', Value: `${this.projectName}-ecs-sg` }]
      }]
    }).promise();

    await this.ec2.authorizeSecurityGroupIngress({
      GroupId: ecsSg.GroupId!,
      IpPermissions: [{
        IpProtocol: 'tcp',
        FromPort: this.containerPort,
        ToPort: this.containerPort,
        UserIdGroupPairs: [{ GroupId: albSg.GroupId! }]
      }]
    }).promise();

    // Remove default egress rule and add custom egress rules
    try {
      // First, remove the default "allow all" egress rule that might not work properly
      await this.ec2.revokeSecurityGroupEgress({
        GroupId: ecsSg.GroupId!,
        IpPermissions: [
          {
            IpProtocol: '-1',
            IpRanges: [{ CidrIp: '0.0.0.0/0' }]
          }
        ]
      }).promise();
    } catch (error) {
      // Ignore error if rule doesn't exist
      console.log('Default egress rule removal failed (might not exist):', error);
    }

    // Add specific egress rules for ECS to access external services
    await this.ec2.authorizeSecurityGroupEgress({
      GroupId: ecsSg.GroupId!,
      IpPermissions: [
        {
          // Allow ALL outbound traffic
          IpProtocol: '-1',
          IpRanges: [{ CidrIp: '0.0.0.0/0' }]
        }
      ]
    }).promise();

    return {
      albSecurityGroupId: albSg.GroupId!,
      ecsSecurityGroupId: ecsSg.GroupId!
    };
  }

  private async createOrUpdateIAMRoles() {
    const taskRoleArn = await this.createOrUpdateTaskRole();
    const executionRoleArn = await this.createOrUpdateExecutionRole();

    return { taskRoleArn, executionRoleArn };
  }

  private async createOrUpdateTaskRole(): Promise<string> {
    const roleName = `${this.projectName}-task-role`;
    
    try {
      // Check if role already exists
      const role = await this.iam.getRole({ RoleName: roleName }).promise();
      console.log(`Found existing task role: ${roleName}`);
      
      // Update the inline policy for ECS exec access
      await this.attachECSExecPolicy(roleName);
      
      return role.Role.Arn!;
    } catch (error: any) {
      if (error.code === 'NoSuchEntity') {
        console.log(`Creating new task role: ${roleName}`);
        
        // Create the role
        const roleResult = await this.iam.createRole({
          RoleName: roleName,
          AssumeRolePolicyDocument: JSON.stringify({
            Version: '2012-10-17',
            Statement: [{
              Action: 'sts:AssumeRole',
              Effect: 'Allow',
              Principal: { Service: 'ecs-tasks.amazonaws.com' }
            }]
          }),
          Tags: [{ Key: 'Name', Value: roleName }]
        }).promise();

        // Attach ECS exec policy
        await this.attachECSExecPolicy(roleName);

        console.log(`Created task role: ${roleResult.Role.Arn}`);
        return roleResult.Role.Arn!;
      } else {
        throw error;
      }
    }
  }

  private async attachECSExecPolicy(roleName: string): Promise<void> {
    const policyName = `${this.projectName}-ecs-exec-policy`;
    
    const ecsExecPolicy = {
      Version: '2012-10-17',
      Statement: [
        {
          Effect: 'Allow',
          Action: [
            'ssmmessages:CreateControlChannel',
            'ssmmessages:CreateDataChannel',
            'ssmmessages:OpenControlChannel',
            'ssmmessages:OpenDataChannel'
          ],
          Resource: '*'
        }
      ]
    };

    try {
      // Try to update existing policy
      await this.iam.putRolePolicy({
        RoleName: roleName,
        PolicyName: policyName,
        PolicyDocument: JSON.stringify(ecsExecPolicy)
      }).promise();
      
      console.log(`Updated ECS exec policy for role: ${roleName}`);
    } catch (error) {
      console.error(`Failed to attach ECS exec policy: ${error}`);
      throw error;
    }
  }

  private async createOrUpdateExecutionRole(): Promise<string> {
    const roleName = `${this.projectName}-execution-role`;
    const accountId = await this.getAccountId();
    
    try {
      // Check if role already exists
      const role = await this.iam.getRole({ RoleName: roleName }).promise();
      console.log(`Found existing execution role: ${roleName}`);
      
      // Update the inline policy for Secrets Manager access
      await this.attachSecretsManagerPolicy(roleName, accountId);
      
      return role.Role.Arn!;
    } catch (error: any) {
      if (error.code === 'NoSuchEntity') {
        console.log(`Creating new execution role: ${roleName}`);
        
        // Create the role
        const roleResult = await this.iam.createRole({
          RoleName: roleName,
          AssumeRolePolicyDocument: JSON.stringify({
            Version: '2012-10-17',
            Statement: [{
              Action: 'sts:AssumeRole',
              Effect: 'Allow',
              Principal: { Service: 'ecs-tasks.amazonaws.com' }
            }]
          }),
          Tags: [{ Key: 'Name', Value: roleName }]
        }).promise();

        // Attach the basic ECS task execution policy
        await this.iam.attachRolePolicy({
          RoleName: roleName,
          PolicyArn: 'arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy'
        }).promise();

        // Attach Secrets Manager policy
        await this.attachSecretsManagerPolicy(roleName, accountId);

        console.log(`Created execution role: ${roleResult.Role.Arn}`);
        return roleResult.Role.Arn!;
      } else {
        throw error;
      }
    }
  }

  private async attachSecretsManagerPolicy(roleName: string, accountId: string): Promise<void> {
    const policyName = `${this.projectName}-secrets-policy`;
    
    const secretsPolicy = {
      Version: '2012-10-17',
      Statement: [
        {
          Effect: 'Allow',
          Action: [
            'secretsmanager:GetSecretValue'
          ],
          Resource: [
            `arn:aws:secretsmanager:${this.region}:${accountId}:secret:${this.projectName}/*`
          ]
        }
      ]
    };

    try {
      // Try to update existing policy
      await this.iam.putRolePolicy({
        RoleName: roleName,
        PolicyName: policyName,
        PolicyDocument: JSON.stringify(secretsPolicy)
      }).promise();
      
      console.log(`Updated Secrets Manager policy for role: ${roleName}`);
    } catch (error) {
      console.error(`Failed to attach Secrets Manager policy: ${error}`);
      throw error;
    }
  }

  private async createOrUpdateIAMRole(roleName: string, assumeRolePolicy: any, managedPolicies: string[]) {
    try {
      // Check if role already exists
      const role = await this.iam.getRole({ RoleName: roleName }).promise();
      console.log(`Found existing IAM role: ${roleName}`);
      
      // Ensure managed policies are attached
      for (const policyArn of managedPolicies) {
        try {
          await this.iam.attachRolePolicy({ RoleName: roleName, PolicyArn: policyArn }).promise();
        } catch (error) {
          // Policy might already be attached
        }
      }
      
      return role.Role.Arn;
    } catch (error) {
      // Role doesn't exist, create it
      console.log(`Creating new IAM role: ${roleName}`);
      
      const role = await this.iam.createRole({
        RoleName: roleName,
        AssumeRolePolicyDocument: JSON.stringify(assumeRolePolicy),
        Tags: [{ Key: 'Name', Value: roleName }]
      }).promise();

      // Attach managed policies
      for (const policyArn of managedPolicies) {
        await this.iam.attachRolePolicy({ RoleName: roleName, PolicyArn: policyArn }).promise();
      }

      return role.Role.Arn;
    }
  }

  private async createIAMRoles() {
    const taskRole = await this.iam.createRole({
      RoleName: `${this.projectName}-task-role`,
      AssumeRolePolicyDocument: JSON.stringify({
        Version: '2012-10-17',
        Statement: [{
          Action: 'sts:AssumeRole',
          Effect: 'Allow',
          Principal: { Service: 'ecs-tasks.amazonaws.com' }
        }]
      }),
      Tags: [{ Key: 'Name', Value: `${this.projectName}-task-role` }]
    }).promise();

    const executionRole = await this.iam.createRole({
      RoleName: `${this.projectName}-execution-role`,
      AssumeRolePolicyDocument: JSON.stringify({
        Version: '2012-10-17',
        Statement: [{
          Action: 'sts:AssumeRole',
          Effect: 'Allow',
          Principal: { Service: 'ecs-tasks.amazonaws.com' }
        }]
      }),
      Tags: [{ Key: 'Name', Value: `${this.projectName}-execution-role` }]
    }).promise();

    await this.iam.attachRolePolicy({
      RoleName: executionRole.Role!.RoleName!,
      PolicyArn: 'arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy'
    }).promise();

    return {
      taskRoleArn: taskRole.Role!.Arn!,
      executionRoleArn: executionRole.Role!.Arn!
    };
  }

  private async createOrUpdateLogGroup() {
    const logGroupName = `/ecs/${this.projectName}`;
    
    try {
      // Check if log group exists
      const response = await this.logs.describeLogGroups({ 
        logGroupNamePrefix: logGroupName 
      }).promise();
      
      // Check if the exact log group exists in the response
      const existingLogGroup = response.logGroups?.find(lg => lg.logGroupName === logGroupName);
      
      if (existingLogGroup) {
        console.log(`Found existing log group: ${logGroupName}`);
        return;
      }
      
      // Log group doesn't exist, create it
      console.log(`Creating new log group: ${logGroupName}`);
      
      await this.logs.createLogGroup({
        logGroupName,
        tags: { Name: `${this.projectName}-logs` }
      }).promise();
      
      await this.logs.putRetentionPolicy({
        logGroupName,
        retentionInDays: 7
      }).promise();
      
      console.log(`✅ Created log group: ${logGroupName}`);
      
    } catch (error) {
      console.error(`Error managing log group: ${error}`);
      // Try to create it anyway
      try {
        console.log(`Attempting to create log group: ${logGroupName}`);
        
        await this.logs.createLogGroup({
          logGroupName,
          tags: { Name: `${this.projectName}-logs` }
        }).promise();
        
        await this.logs.putRetentionPolicy({
          logGroupName,
          retentionInDays: 7
        }).promise();
        
        console.log(`✅ Created log group: ${logGroupName}`);
      } catch (createError) {
        console.error(`Failed to create log group: ${createError}`);
        throw createError;
      }
    }
  }

  private async createLogGroup() {
    await this.logs.createLogGroup({
      logGroupName: `/ecs/${this.projectName}`,
      tags: { Name: `${this.projectName}-logs` }
    }).promise();
    
    await this.logs.putRetentionPolicy({
      logGroupName: `/ecs/${this.projectName}`,
      retentionInDays: 7
    }).promise();
  }

  private async createOrUpdateECSCluster() {
    try {
      // Check if cluster exists
      const clusters = await this.ecs.describeClusters({
        clusters: [`${this.projectName}-cluster`]
      }).promise();

      // AWS returns empty clusters array if cluster doesn't exist, not an error
      if (clusters.clusters && clusters.clusters.length > 0) {
        const cluster = clusters.clusters[0];
        // Check if cluster actually exists (not just returned in response)
        if (cluster.clusterName && cluster.status === 'ACTIVE') {
          console.log(`Found existing ECS cluster: ${cluster.clusterArn}`);
          return { cluster };
        }
      }
      
      console.log('No existing ECS cluster found, creating new one');
    } catch (error) {
      console.log('Error checking for existing cluster, creating new one:', error);
    }

    return this.createECSCluster();
  }

  private async createECSCluster() {
    console.log(`Creating ECS cluster: ${this.projectName}-cluster in region ${this.region}`);
    const result = await this.ecs.createCluster({
      clusterName: `${this.projectName}-cluster`,
      tags: [{ key: 'Name', value: `${this.projectName}-cluster` }]
    }).promise();
    
    console.log(`Created ECS cluster: ${result.cluster?.clusterArn}`);
    return result;
  }

  private async createTaskDefinition(roles: { taskRoleArn: string; executionRoleArn: string }) {
    // Prepare environment variables and secrets
    const environment: AWS.ECS.KeyValuePair[] = [];
    const secrets: AWS.ECS.Secret[] = [];

    if (this.args.environmentVariables) {
      for (const envVar of this.args.environmentVariables) {
        if (envVar.isSecret && envVar.secretKey) {
          // Add to secrets array for AWS Secrets Manager
          // The ARN format should include the full secret ARN with suffix
          secrets.push({
            name: envVar.key,
            valueFrom: await this.getSecretArn(envVar.secretKey)
          });
        } else if (!envVar.isSecret && envVar.value) {
          // Add to environment array for regular environment variables
          environment.push({
            name: envVar.key,
            value: envVar.value
          });
        }
      }
    }

    const containerDef: AWS.ECS.ContainerDefinition = {
      name: this.projectName,
      image: this.imageUri,
      portMappings: [{
        containerPort: this.containerPort,
        protocol: 'tcp'
      }],
      essential: true,
      logConfiguration: {
        logDriver: 'awslogs',
        options: {
          'awslogs-group': `/ecs/${this.projectName}`,
          'awslogs-region': this.region,
          'awslogs-stream-prefix': 'ecs'
        }
      }
    };

    // Add environment variables if any
    if (environment.length > 0) {
      containerDef.environment = environment;
    }

    // Add secrets if any
    if (secrets.length > 0) {
      containerDef.secrets = secrets;
    }

    return await this.ecs.registerTaskDefinition({
      family: `${this.projectName}-task`,
      networkMode: 'awsvpc',
      requiresCompatibilities: ['FARGATE'],
      cpu: '256',
      memory: '512',
      executionRoleArn: roles.executionRoleArn,
      taskRoleArn: roles.taskRoleArn,
      containerDefinitions: [containerDef],
      tags: [{ key: 'Name', value: `${this.projectName}-task` }]
    }).promise();
  }

  private async getAccountId(): Promise<string> {
    const sts = new AWS.STS();
    const identity = await sts.getCallerIdentity().promise();
    return identity.Account!;
  }

  private async getSecretArn(secretName: string): Promise<string> {
    try {
      const secretsManager = new AWS.SecretsManager({ region: this.region });
      const result = await secretsManager.describeSecret({
        SecretId: secretName
      }).promise();
      
      if (!result.ARN) {
        throw new Error(`Could not get ARN for secret: ${secretName}`);
      }
      
      return result.ARN;
    } catch (error) {
      console.error(`Failed to get secret ARN for ${secretName}:`, error);
      // Fallback to constructed ARN (though this might not work)
      const accountId = await this.getAccountId();
      return `arn:aws:secretsmanager:${this.region}:${accountId}:secret:${secretName}`;
    }
  }

  private async createLoadBalancer(subnets: string[], securityGroupId: string) {
    return await this.elbv2.createLoadBalancer({
      Name: `${this.projectName}-alb`,
      Subnets: subnets,
      SecurityGroups: [securityGroupId],
      Tags: [{ Key: 'Name', Value: `${this.projectName}-alb` }]
    }).promise();
  }

  private async createTargetGroup(vpcId: string) {
    return await this.elbv2.createTargetGroup({
      Name: `${this.projectName}-tg`,
      Port: this.containerPort,
      Protocol: 'HTTP',
      VpcId: vpcId,
      TargetType: 'ip',
      HealthCheckEnabled: true,
      HealthCheckIntervalSeconds: 30,
      HealthCheckPath: '/',
      HealthCheckPort: 'traffic-port',
      HealthCheckProtocol: 'HTTP',
      HealthCheckTimeoutSeconds: 5,
      HealthyThresholdCount: 2,
      UnhealthyThresholdCount: 2,
      Matcher: { HttpCode: '200' },
      Tags: [{ Key: 'Name', Value: `${this.projectName}-tg` }]
    }).promise();
  }

  private async createListener(loadBalancerArn: string, targetGroupArn: string) {
    return await this.elbv2.createListener({
      LoadBalancerArn: loadBalancerArn,
      Port: 80,
      Protocol: 'HTTP',
      DefaultActions: [{
        Type: 'forward',
        TargetGroupArn: targetGroupArn
      }],
      Tags: [{ Key: 'Name', Value: `${this.projectName}-listener` }]
    }).promise();
  }

  private async createOrUpdateECSService(
    clusterArn: string,
    taskDefinitionArn: string,
    subnets: string[],
    securityGroupId: string,
    targetGroupArn: string
  ) {
    const serviceName = `${this.projectName}-service`;
    
    try {
      // Check if service already exists
      const existingServices = await this.ecs.describeServices({
        cluster: clusterArn,
        services: [serviceName]
      }).promise();
      
      if (existingServices.services && existingServices.services.length > 0) {
        const existingService = existingServices.services[0];
        
        if (existingService.status === 'ACTIVE') {
          console.log(`Updating existing ECS service: ${existingService.serviceArn}`);
          
          // Update the service with new task definition
          const updateResponse = await this.ecs.updateService({
            cluster: clusterArn,
            service: serviceName,
            taskDefinition: taskDefinitionArn,
            desiredCount: 1,
            enableExecuteCommand: true
          }).promise();
          
          console.log('Service updated, waiting for deployment to stabilize...');
          await this.waitForServiceStability(clusterArn, serviceName);
          
          return updateResponse;
        }
      }
    } catch (error) {
      console.log('No existing service found or error checking, creating new service');
    }
    
    // Create new service if it doesn't exist
    return this.createECSService(clusterArn, taskDefinitionArn, subnets, securityGroupId, targetGroupArn);
  }

  private async createECSService(
    clusterArn: string,
    taskDefinitionArn: string,
    subnets: string[],
    securityGroupId: string,
    targetGroupArn: string
  ) {
    console.log(`Creating ECS service in cluster: ${clusterArn}`);
    console.log(`Using task definition: ${taskDefinitionArn}`);
    console.log(`Subnets: ${subnets.join(', ')}`);
    console.log(`Security group: ${securityGroupId}`);
    console.log(`Target group: ${targetGroupArn}`);
    
    const serviceResponse = await this.ecs.createService({
      serviceName: `${this.projectName}-service`,
      cluster: clusterArn,
      taskDefinition: taskDefinitionArn,
      desiredCount: 1,
      launchType: 'FARGATE',
      enableExecuteCommand: true,
      networkConfiguration: {
        awsvpcConfiguration: {
          subnets: subnets,
          securityGroups: [securityGroupId],
          assignPublicIp: 'ENABLED'
        }
      },
      loadBalancers: [{
        targetGroupArn: targetGroupArn,
        containerName: this.projectName,
        containerPort: this.containerPort
      }],
      tags: [{ key: 'Name', value: `${this.projectName}-service` }]
    }).promise();

    console.log(`ECS service created: ${serviceResponse.service?.serviceArn}`);
    console.log('Waiting for service deployment to become stable...');
    
    // Wait for the service to become stable
    await this.waitForServiceStability(clusterArn, `${this.projectName}-service`);
    
    return serviceResponse;
  }

  private async waitForServiceStability(clusterArn: string, serviceName: string, maxWaitTime: number = 600): Promise<void> {
    console.log(`Waiting for ECS service ${serviceName} to become stable (max ${maxWaitTime}s)...`);
    
    const startTime = Date.now();
    const checkInterval = 30000; // Check every 30 seconds
    let attempts = 0;
    
    while (Date.now() - startTime < maxWaitTime * 1000) {
      attempts++;
      
      try {
        console.log(`Stability check attempt ${attempts}...`);
        
        // Check service status
        const services = await this.ecs.describeServices({
          cluster: clusterArn,
          services: [serviceName]
        }).promise();
        
        if (!services.services || services.services.length === 0) {
          throw new Error(`Service ${serviceName} not found`);
        }
        
        const service = services.services[0];
        const runningCount = service.runningCount || 0;
        const desiredCount = service.desiredCount || 0;
        const deploymentStatus = service.deployments?.[0]?.status || 'UNKNOWN';
        
        console.log(`Service status: Running=${runningCount}/${desiredCount}, Deployment=${deploymentStatus}`);
        
        // Check if service is stable
        if (runningCount === desiredCount && runningCount > 0) {
          // Check deployment status
          const primaryDeployment = service.deployments?.find(d => d.status === 'PRIMARY');
          if (primaryDeployment && primaryDeployment.runningCount === primaryDeployment.desiredCount) {
            console.log('✅ ECS service deployment is stable!');
            
            // Additional check: ensure tasks are healthy by checking target group health
            await this.checkTargetGroupHealth(serviceName);
            
            return;
          }
        }
        
        // Check for failed deployments
        const failedDeployment = service.deployments?.find(d => d.status === 'FAILED');
        if (failedDeployment) {
          throw new Error(`Deployment failed: ${failedDeployment.status}`);
        }
        
        console.log(`Service not yet stable, waiting ${checkInterval / 1000}s before next check...`);
        await new Promise(resolve => setTimeout(resolve, checkInterval));
        
      } catch (error) {
        console.error(`Error checking service stability: ${error}`);
        throw error;
      }
    }
    
    throw new Error(`Service ${serviceName} did not become stable within ${maxWaitTime} seconds`);
  }

  private async checkTargetGroupHealth(serviceName: string): Promise<void> {
    try {
      // Get target groups for this service
      const targetGroups = await this.elbv2.describeTargetGroups({
        Names: [`${this.projectName}-tg`]
      }).promise();
      
      if (targetGroups.TargetGroups && targetGroups.TargetGroups.length > 0) {
        const targetGroup = targetGroups.TargetGroups[0];
        
        // Check target health
        const health = await this.elbv2.describeTargetHealth({
          TargetGroupArn: targetGroup.TargetGroupArn!
        }).promise();
        
        const healthyTargets = health.TargetHealthDescriptions?.filter(t => t.TargetHealth?.State === 'healthy').length || 0;
        const totalTargets = health.TargetHealthDescriptions?.length || 0;
        
        console.log(`Target group health: ${healthyTargets}/${totalTargets} targets healthy`);
        
        if (healthyTargets === 0 && totalTargets > 0) {
          console.warn('⚠️ Service is running but targets are not yet healthy. This may take a few more minutes.');
        } else if (healthyTargets > 0) {
          console.log('✅ Service targets are healthy!');
        }
      }
    } catch (error) {
      console.warn('Could not check target group health:', error);
      // Don't fail the deployment for target group health check issues
    }
  }

  async destroyInfrastructure(): Promise<void> {
    console.log('Infrastructure destruction would need to be implemented');
  }
}