import * as AWS from 'aws-sdk';
import { EnvironmentVariable } from "../types";

export interface VPCServiceConfig {
  projectName: string;
  environmentVariables: EnvironmentVariable[];
  region?: string;
  existingVpcId?: string;
  existingSubnetIds?: string[];
}

export class VPCService {
  private ec2: AWS.EC2;
  private projectName: string;
  private region: string;
  public vpcId: string;
  public subnetIds: string[];
  public securityGroupIds: { albSecurityGroupId: string; ecsSecurityGroupId: string };

  constructor(private config: VPCServiceConfig) {
    this.projectName = config.projectName;
    this.region = config.region || 'us-east-1';
    
    AWS.config.update({ region: this.region });
    this.ec2 = new AWS.EC2();
  }

  async initialize(): Promise<void> {
    // Set up VPC
    if (this.config.existingVpcId) {
      this.vpcId = this.config.existingVpcId;
      console.log(`Using existing VPC: ${this.vpcId}`);
    } else {
      this.vpcId = await this.createOrFindVPC();
    }

    // Set up subnets
    if (this.config.existingSubnetIds && this.config.existingSubnetIds.length >= 2) {
      this.subnetIds = this.config.existingSubnetIds;
      console.log(`Using existing subnets: ${this.subnetIds.join(', ')}`);
    } else {
      this.subnetIds = await this.createOrFindSubnets();
    }

    // Set up networking (IGW, routes) if we created a new VPC
    if (!this.config.existingVpcId) {
      await this.setupNetworking();
    }

    // Set up security groups
    this.securityGroupIds = await this.createOrUpdateSecurityGroups();
  }

  private async createOrFindVPC(): Promise<string> {
    try {
      // Check if VPC already exists
      const vpcs = await this.ec2.describeVpcs({
        Filters: [
          { Name: 'tag:Name', Values: [`${this.projectName}-vpc`] },
          { Name: 'state', Values: ['available'] }
        ]
      }).promise();

      if (vpcs.Vpcs && vpcs.Vpcs.length > 0) {
        console.log(`Found existing VPC: ${vpcs.Vpcs[0].VpcId}`);
        return vpcs.Vpcs[0].VpcId!;
      }
    } catch (error) {
      console.log('No existing VPC found, creating new one');
    }

    // Create new VPC
    const vpc = await this.ec2.createVpc({
      CidrBlock: '10.0.0.0/16',
      TagSpecifications: [{
        ResourceType: 'vpc',
        Tags: [{ Key: 'Name', Value: `${this.projectName}-vpc` }]
      }]
    }).promise();

    const vpcId = vpc.Vpc!.VpcId!;

    // Enable DNS support
    await this.ec2.modifyVpcAttribute({
      VpcId: vpcId,
      EnableDnsHostnames: { Value: true }
    }).promise();

    await this.ec2.modifyVpcAttribute({
      VpcId: vpcId,
      EnableDnsSupport: { Value: true }
    }).promise();

    console.log(`Created new VPC: ${vpcId}`);
    return vpcId;
  }

  private async createOrFindSubnets(): Promise<string[]> {
    try {
      // Check if subnets already exist
      const subnets = await this.ec2.describeSubnets({
        Filters: [
          { Name: 'vpc-id', Values: [this.vpcId] },
          { Name: 'tag:Name', Values: [`${this.projectName}-public-subnet-1`, `${this.projectName}-public-subnet-2`] },
          { Name: 'state', Values: ['available'] }
        ]
      }).promise();

      if (subnets.Subnets && subnets.Subnets.length >= 2) {
        const subnetIds = subnets.Subnets.map(s => s.SubnetId!).sort();
        console.log(`Found existing subnets: ${subnetIds.join(', ')}`);
        return subnetIds;
      }
    } catch (error) {
      console.log('No existing subnets found, creating new ones');
    }

    // Create new subnets
    const subnet1 = await this.ec2.createSubnet({
      VpcId: this.vpcId,
      CidrBlock: '10.0.1.0/24',
      AvailabilityZone: `${this.region}a`,
      TagSpecifications: [{
        ResourceType: 'subnet',
        Tags: [{ Key: 'Name', Value: `${this.projectName}-public-subnet-1` }]
      }]
    }).promise();

    const subnet2 = await this.ec2.createSubnet({
      VpcId: this.vpcId,
      CidrBlock: '10.0.2.0/24',
      AvailabilityZone: `${this.region}b`,
      TagSpecifications: [{
        ResourceType: 'subnet',
        Tags: [{ Key: 'Name', Value: `${this.projectName}-public-subnet-2` }]
      }]
    }).promise();

    // Enable auto-assign public IP
    await this.ec2.modifySubnetAttribute({
      SubnetId: subnet1.Subnet!.SubnetId!,
      MapPublicIpOnLaunch: { Value: true }
    }).promise();

    await this.ec2.modifySubnetAttribute({
      SubnetId: subnet2.Subnet!.SubnetId!,
      MapPublicIpOnLaunch: { Value: true }
    }).promise();

    const subnetIds = [subnet1.Subnet!.SubnetId!, subnet2.Subnet!.SubnetId!];
    console.log(`Created new subnets: ${subnetIds.join(', ')}`);
    return subnetIds;
  }

  private async setupNetworking(): Promise<void> {
    // Get or create internet gateway
    const igwId = await this.getOrCreateInternetGateway();
    
    // Get or create route table and ensure proper routes
    await this.getOrCreateRouteTable(igwId);

    console.log('Networking setup complete');
  }

  private async getOrCreateInternetGateway(): Promise<string> {
    try {
      // Check if IGW already exists and is attached to this VPC
      const igws = await this.ec2.describeInternetGateways({
        Filters: [
          { Name: 'attachment.vpc-id', Values: [this.vpcId] }
        ]
      }).promise();

      if (igws.InternetGateways && igws.InternetGateways.length > 0) {
        const igw = igws.InternetGateways[0];
        console.log(`Found existing internet gateway: ${igw.InternetGatewayId}`);
        return igw.InternetGatewayId!;
      }
    } catch (error) {
      console.log('No existing internet gateway found');
    }

    // Create new internet gateway
    console.log('Creating new internet gateway');
    const igw = await this.ec2.createInternetGateway({
      TagSpecifications: [{
        ResourceType: 'internet-gateway',
        Tags: [{ Key: 'Name', Value: `${this.projectName}-igw` }]
      }]
    }).promise();

    await this.ec2.attachInternetGateway({
      VpcId: this.vpcId,
      InternetGatewayId: igw.InternetGateway!.InternetGatewayId!
    }).promise();

    console.log(`Created and attached new internet gateway: ${igw.InternetGateway!.InternetGatewayId}`);
    return igw.InternetGateway!.InternetGatewayId!;
  }

  private async getOrCreateRouteTable(igwId: string): Promise<void> {
    try {
      // Check if custom route table already exists for this project
      const routeTables = await this.ec2.describeRouteTables({
        Filters: [
          { Name: 'vpc-id', Values: [this.vpcId] },
          { Name: 'tag:Name', Values: [`${this.projectName}-public-rt`] }
        ]
      }).promise();

      if (routeTables.RouteTables && routeTables.RouteTables.length > 0) {
        const routeTable = routeTables.RouteTables[0];
        console.log(`Found existing route table: ${routeTable.RouteTableId}`);
        
        // Ensure IGW route exists
        await this.ensureInternetRoute(routeTable.RouteTableId!, igwId);
        
        // Ensure subnet associations
        await this.ensureSubnetAssociations(routeTable.RouteTableId!);
        return;
      }
    } catch (error) {
      console.log('No existing custom route table found');
    }

    // Check if subnets are already associated with a route table that has internet access
    const hasInternetAccess = await this.checkSubnetsHaveInternetAccess(igwId);
    if (hasInternetAccess) {
      console.log('Subnets already have internet access via existing route table');
      return;
    }

    // Create new route table
    console.log('Creating new route table');
    const routeTable = await this.ec2.createRouteTable({
      VpcId: this.vpcId,
      TagSpecifications: [{
        ResourceType: 'route-table',
        Tags: [{ Key: 'Name', Value: `${this.projectName}-public-rt` }]
      }]
    }).promise();

    await this.ensureInternetRoute(routeTable.RouteTable!.RouteTableId!, igwId);
    await this.ensureSubnetAssociations(routeTable.RouteTable!.RouteTableId!);
  }

  private async ensureInternetRoute(routeTableId: string, igwId: string): Promise<void> {
    try {
      // Check if internet route already exists
      const routeTable = await this.ec2.describeRouteTables({
        RouteTableIds: [routeTableId]
      }).promise();

      const hasInternetRoute = routeTable.RouteTables?.[0]?.Routes?.some(route => 
        route.DestinationCidrBlock === '0.0.0.0/0' && route.GatewayId === igwId
      );

      if (hasInternetRoute) {
        console.log('Internet route already exists');
        return;
      }

      // Create internet route
      await this.ec2.createRoute({
        RouteTableId: routeTableId,
        DestinationCidrBlock: '0.0.0.0/0',
        GatewayId: igwId
      }).promise();

      console.log('Created internet route');
    } catch (error: any) {
      if (error.code === 'RouteAlreadyExists') {
        console.log('Internet route already exists');
      } else {
        throw error;
      }
    }
  }

  private async ensureSubnetAssociations(routeTableId: string): Promise<void> {
    for (const subnetId of this.subnetIds) {
      try {
        // Check if subnet is already associated with this route table
        const associations = await this.ec2.describeRouteTables({
          Filters: [
            { Name: 'association.subnet-id', Values: [subnetId] },
            { Name: 'route-table-id', Values: [routeTableId] }
          ]
        }).promise();

        if (associations.RouteTables && associations.RouteTables.length > 0) {
          console.log(`Subnet ${subnetId} already associated with route table`);
          continue;
        }

        // Associate subnet with route table
        await this.ec2.associateRouteTable({
          RouteTableId: routeTableId,
          SubnetId: subnetId
        }).promise();

        console.log(`Associated subnet ${subnetId} with route table`);
      } catch (error: any) {
        if (error.code === 'Resource.AlreadyAssociated') {
          console.log(`Subnet ${subnetId} already associated with a route table`);
        } else {
          throw error;
        }
      }
    }
  }

  private async checkSubnetsHaveInternetAccess(igwId: string): Promise<boolean> {
    for (const subnetId of this.subnetIds) {
      // Get the route table associated with this subnet
      const routeTables = await this.ec2.describeRouteTables({
        Filters: [
          { Name: 'association.subnet-id', Values: [subnetId] }
        ]
      }).promise();

      if (!routeTables.RouteTables || routeTables.RouteTables.length === 0) {
        return false; // No route table associated
      }

      const routeTable = routeTables.RouteTables[0];
      const hasInternetRoute = routeTable.Routes?.some(route => 
        route.DestinationCidrBlock === '0.0.0.0/0' && route.GatewayId === igwId
      );

      if (!hasInternetRoute) {
        return false; // No internet route
      }
    }

    return true; // All subnets have internet access
  }

  private async createOrUpdateSecurityGroups(): Promise<{ albSecurityGroupId: string; ecsSecurityGroupId: string }> {
    const albSg = await this.createOrUpdateSecurityGroup(
      `${this.projectName}-alb-sg`,
      'ALB Security Group',
      [
        { IpProtocol: 'tcp', FromPort: 80, ToPort: 80, IpRanges: [{ CidrIp: '0.0.0.0/0' }] },
        { IpProtocol: 'tcp', FromPort: 443, ToPort: 443, IpRanges: [{ CidrIp: '0.0.0.0/0' }] }
      ]
    );

    const ecsSg = await this.createOrUpdateSecurityGroup(
      `${this.projectName}-ecs-sg`,
      'ECS Security Group',
      [
        { IpProtocol: 'tcp', FromPort: 3000, ToPort: 3000, UserIdGroupPairs: [{ GroupId: albSg }] }
      ]
    );

    return {
      albSecurityGroupId: albSg,
      ecsSecurityGroupId: ecsSg
    };
  }

  private async createOrUpdateSecurityGroup(name: string, description: string, rules: any[]): Promise<string> {
    try {
      // Check if security group already exists
      const sgs = await this.ec2.describeSecurityGroups({
        Filters: [
          { Name: 'group-name', Values: [name] },
          { Name: 'vpc-id', Values: [this.vpcId] }
        ]
      }).promise();

      if (sgs.SecurityGroups && sgs.SecurityGroups.length > 0) {
        const sg = sgs.SecurityGroups[0];
        console.log(`Found existing security group: ${sg.GroupId}`);
        return sg.GroupId!;
      }
    } catch (error) {
      console.log(`No existing security group found for ${name}, creating new one`);
    }

    // Create new security group
    const sg = await this.ec2.createSecurityGroup({
      GroupName: name,
      Description: description,
      VpcId: this.vpcId,
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
}