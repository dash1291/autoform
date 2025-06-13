import { VPCService } from '../../services/vpc-service';
import { setupLocalStackAWS, waitForResource, generateTestProjectName } from '../test-utils';

describe('VPCService Integration Tests', () => {
  let aws: ReturnType<typeof setupLocalStackAWS>;
  let projectName: string;

  beforeAll(() => {
    aws = setupLocalStackAWS();
    projectName = generateTestProjectName();
  });

  afterEach(async () => {
    // Cleanup resources after each test
    try {
      // Delete VPC and related resources
      const vpcs = await aws.ec2.describeVpcs({
        Filters: [{ Name: 'tag:Name', Values: [`${projectName}-vpc`] }]
      }).promise();

      for (const vpc of vpcs.Vpcs || []) {
        if (vpc.VpcId) {
          try {
            // Delete subnets
            const subnets = await aws.ec2.describeSubnets({
              Filters: [{ Name: 'vpc-id', Values: [vpc.VpcId] }]
            }).promise();

            for (const subnet of subnets.Subnets || []) {
              if (subnet.SubnetId) {
                await aws.ec2.deleteSubnet({ SubnetId: subnet.SubnetId }).promise();
              }
            }

            // Delete security groups (except default)
            const securityGroups = await aws.ec2.describeSecurityGroups({
              Filters: [
                { Name: 'vpc-id', Values: [vpc.VpcId] },
                { Name: 'group-name', Values: [`${projectName}-*`] }
              ]
            }).promise();

            for (const sg of securityGroups.SecurityGroups || []) {
              if (sg.GroupId && sg.GroupName !== 'default') {
                await aws.ec2.deleteSecurityGroup({ GroupId: sg.GroupId }).promise();
              }
            }

            // Detach and delete internet gateway
            const igws = await aws.ec2.describeInternetGateways({
              Filters: [{ Name: 'attachment.vpc-id', Values: [vpc.VpcId] }]
            }).promise();

            for (const igw of igws.InternetGateways || []) {
              if (igw.InternetGatewayId) {
                await aws.ec2.detachInternetGateway({
                  VpcId: vpc.VpcId,
                  InternetGatewayId: igw.InternetGatewayId
                }).promise();
                await aws.ec2.deleteInternetGateway({
                  InternetGatewayId: igw.InternetGatewayId
                }).promise();
              }
            }

            // Delete custom route tables
            const routeTables = await aws.ec2.describeRouteTables({
              Filters: [
                { Name: 'vpc-id', Values: [vpc.VpcId] },
                { Name: 'tag:Name', Values: [`${projectName}-*`] }
              ]
            }).promise();

            for (const rt of routeTables.RouteTables || []) {
              if (rt.RouteTableId) {
                await aws.ec2.deleteRouteTable({ RouteTableId: rt.RouteTableId }).promise();
              }
            }

            // Finally delete VPC
            await aws.ec2.deleteVpc({ VpcId: vpc.VpcId }).promise();
          } catch (error) {
            console.log('Cleanup error (expected in LocalStack):', error);
          }
        }
      }
    } catch (error) {
      console.log('Cleanup error (expected in LocalStack):', error);
    }
  });

  describe('VPC Creation', () => {
    test('should create a new VPC with proper configuration', async () => {
      const vpcService = new VPCService({
        projectName,
        environmentVariables: [],
        region: 'us-east-1'
      });

      await vpcService.initialize();

      // Verify VPC was created
      expect(vpcService.vpcId).toBeDefined();
      expect(vpcService.vpcId).toMatch(/^vpc-/);

      // Verify VPC exists in AWS
      const vpcs = await aws.ec2.describeVpcs({
        VpcIds: [vpcService.vpcId]
      }).promise();

      expect(vpcs.Vpcs).toHaveLength(1);
      expect(vpcs.Vpcs![0].CidrBlock).toBe('10.0.0.0/16');
      expect(vpcs.Vpcs![0].State).toBe('available');
    });

    test('should use existing VPC when provided', async () => {
      // First create a VPC manually
      const existingVpc = await aws.ec2.createVpc({
        CidrBlock: '10.1.0.0/16',
        TagSpecifications: [{
          ResourceType: 'vpc',
          Tags: [{ Key: 'Name', Value: `existing-${projectName}-vpc` }]
        }]
      }).promise();

      const vpcService = new VPCService({
        projectName,
        environmentVariables: [],
        region: 'us-east-1',
        existingVpcId: existingVpc.Vpc!.VpcId!
      });

      await vpcService.initialize();

      expect(vpcService.vpcId).toBe(existingVpc.Vpc!.VpcId!);
    });
  });

  describe('Subnet Creation', () => {
    test('should create two subnets in different availability zones', async () => {
      const vpcService = new VPCService({
        projectName,
        environmentVariables: [],
        region: 'us-east-1'
      });

      await vpcService.initialize();

      // Verify subnets were created
      expect(vpcService.subnetIds).toHaveLength(2);
      expect(vpcService.subnetIds[0]).toMatch(/^subnet-/);
      expect(vpcService.subnetIds[1]).toMatch(/^subnet-/);

      // Verify subnets exist in AWS
      const subnets = await aws.ec2.describeSubnets({
        SubnetIds: vpcService.subnetIds
      }).promise();

      expect(subnets.Subnets).toHaveLength(2);
      expect(subnets.Subnets!.map(s => s.CidrBlock)).toEqual(
        expect.arrayContaining(['10.0.1.0/24', '10.0.2.0/24'])
      );
      expect(subnets.Subnets!.map(s => s.AvailabilityZone)).toEqual(
        expect.arrayContaining(['us-east-1a', 'us-east-1b'])
      );
    });

    test('should use existing subnets when provided', async () => {
      // Create VPC first
      const vpc = await aws.ec2.createVpc({ CidrBlock: '10.2.0.0/16' }).promise();
      
      // Create existing subnets
      const subnet1 = await aws.ec2.createSubnet({
        VpcId: vpc.Vpc!.VpcId!,
        CidrBlock: '10.2.1.0/24',
        AvailabilityZone: 'us-east-1a'
      }).promise();

      const subnet2 = await aws.ec2.createSubnet({
        VpcId: vpc.Vpc!.VpcId!,
        CidrBlock: '10.2.2.0/24',
        AvailabilityZone: 'us-east-1b'
      }).promise();

      const vpcService = new VPCService({
        projectName,
        environmentVariables: [],
        region: 'us-east-1',
        existingVpcId: vpc.Vpc!.VpcId!,
        existingSubnetIds: [subnet1.Subnet!.SubnetId!, subnet2.Subnet!.SubnetId!]
      });

      await vpcService.initialize();

      expect(vpcService.subnetIds).toEqual(
        expect.arrayContaining([subnet1.Subnet!.SubnetId!, subnet2.Subnet!.SubnetId!])
      );
    });
  });

  describe('Security Groups', () => {
    test('should create ALB and ECS security groups with correct rules', async () => {
      const vpcService = new VPCService({
        projectName,
        environmentVariables: [],
        region: 'us-east-1'
      });

      await vpcService.initialize();

      // Verify security groups were created
      expect(vpcService.securityGroupIds.albSecurityGroupId).toMatch(/^sg-/);
      expect(vpcService.securityGroupIds.ecsSecurityGroupId).toMatch(/^sg-/);

      // Verify ALB security group rules
      const albSg = await aws.ec2.describeSecurityGroups({
        GroupIds: [vpcService.securityGroupIds.albSecurityGroupId]
      }).promise();

      const albRules = albSg.SecurityGroups![0].IpPermissions!;
      expect(albRules).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            IpProtocol: 'tcp',
            FromPort: 80,
            ToPort: 80
          }),
          expect.objectContaining({
            IpProtocol: 'tcp',
            FromPort: 443,
            ToPort: 443
          })
        ])
      );

      // Verify ECS security group rules
      const ecsSg = await aws.ec2.describeSecurityGroups({
        GroupIds: [vpcService.securityGroupIds.ecsSecurityGroupId]
      }).promise();

      const ecsRules = ecsSg.SecurityGroups![0].IpPermissions!;
      expect(ecsRules).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            IpProtocol: 'tcp',
            FromPort: 3000,
            ToPort: 3000
          })
        ])
      );
    });
  });

  describe('Internet Gateway and Routing', () => {
    test('should create internet gateway and configure routing for new VPC', async () => {
      const vpcService = new VPCService({
        projectName,
        environmentVariables: [],
        region: 'us-east-1'
      });

      await vpcService.initialize();

      // Verify internet gateway exists and is attached
      const igws = await aws.ec2.describeInternetGateways({
        Filters: [{ Name: 'attachment.vpc-id', Values: [vpcService.vpcId] }]
      }).promise();

      expect(igws.InternetGateways).toHaveLength(1);
      expect(igws.InternetGateways![0].Attachments![0].State).toBe('available');

      // Verify route table has internet route
      const routeTables = await aws.ec2.describeRouteTables({
        Filters: [
          { Name: 'vpc-id', Values: [vpcService.vpcId] },
          { Name: 'tag:Name', Values: [`${projectName}-public-rt`] }
        ]
      }).promise();

      expect(routeTables.RouteTables).toHaveLength(1);
      
      const routes = routeTables.RouteTables![0].Routes!;
      const internetRoute = routes.find(route => route.DestinationCidrBlock === '0.0.0.0/0');
      expect(internetRoute).toBeDefined();
      expect(internetRoute!.GatewayId).toBe(igws.InternetGateways![0].InternetGatewayId);
    });
  });
});