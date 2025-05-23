import * as pulumi from "@pulumi/pulumi";
import * as aws from "@pulumi/aws";

export interface ECSInfrastructureArgs {
  projectName: string;
  imageUri: string;
  containerPort?: number;
}

export class ECSInfrastructure extends pulumi.ComponentResource {
  public readonly cluster: aws.ecs.Cluster;
  public readonly service: aws.ecs.Service;
  public readonly loadBalancer: aws.lb.LoadBalancer;
  public readonly targetGroup: aws.lb.TargetGroup;
  public readonly taskDefinition: aws.ecs.TaskDefinition;

  constructor(
    name: string,
    args: ECSInfrastructureArgs,
    opts?: pulumi.ComponentResourceOptions
  ) {
    super("autopilot:infrastructure:ECS", name, {}, opts);

    const containerPort = args.containerPort || 3000;

    // Create VPC
    const vpc = new aws.ec2.Vpc(`${name}-vpc`, {
      cidrBlock: "10.0.0.0/16",
      enableDnsHostnames: true,
      enableDnsSupport: true,
      tags: {
        Name: `${args.projectName}-vpc`,
      },
    }, { parent: this });

    // Create public subnets
    const publicSubnet1 = new aws.ec2.Subnet(`${name}-public-subnet-1`, {
      vpcId: vpc.id,
      cidrBlock: "10.0.1.0/24",
      availabilityZone: "us-east-1a",
      mapPublicIpOnLaunch: true,
      tags: {
        Name: `${args.projectName}-public-subnet-1`,
      },
    }, { parent: this });

    const publicSubnet2 = new aws.ec2.Subnet(`${name}-public-subnet-2`, {
      vpcId: vpc.id,
      cidrBlock: "10.0.2.0/24",
      availabilityZone: "us-east-1b",
      mapPublicIpOnLaunch: true,
      tags: {
        Name: `${args.projectName}-public-subnet-2`,
      },
    }, { parent: this });

    // Internet Gateway
    const igw = new aws.ec2.InternetGateway(`${name}-igw`, {
      vpcId: vpc.id,
      tags: {
        Name: `${args.projectName}-igw`,
      },
    }, { parent: this });

    // Route table for public subnets
    const publicRouteTable = new aws.ec2.RouteTable(`${name}-public-rt`, {
      vpcId: vpc.id,
      routes: [{
        cidrBlock: "0.0.0.0/0",
        gatewayId: igw.id,
      }],
      tags: {
        Name: `${args.projectName}-public-rt`,
      },
    }, { parent: this });

    // Associate route table with subnets
    new aws.ec2.RouteTableAssociation(`${name}-public-rta-1`, {
      subnetId: publicSubnet1.id,
      routeTableId: publicRouteTable.id,
    }, { parent: this });

    new aws.ec2.RouteTableAssociation(`${name}-public-rta-2`, {
      subnetId: publicSubnet2.id,
      routeTableId: publicRouteTable.id,
    }, { parent: this });

    // Security groups
    const albSecurityGroup = new aws.ec2.SecurityGroup(`${name}-alb-sg`, {
      vpcId: vpc.id,
      description: "ALB Security Group",
      ingress: [{
        protocol: "tcp",
        fromPort: 80,
        toPort: 80,
        cidrBlocks: ["0.0.0.0/0"],
      }, {
        protocol: "tcp",
        fromPort: 443,
        toPort: 443,
        cidrBlocks: ["0.0.0.0/0"],
      }],
      egress: [{
        protocol: "-1",
        fromPort: 0,
        toPort: 0,
        cidrBlocks: ["0.0.0.0/0"],
      }],
      tags: {
        Name: `${args.projectName}-alb-sg`,
      },
    }, { parent: this });

    const ecsSecurityGroup = new aws.ec2.SecurityGroup(`${name}-ecs-sg`, {
      vpcId: vpc.id,
      description: "ECS Security Group",
      ingress: [{
        protocol: "tcp",
        fromPort: containerPort,
        toPort: containerPort,
        securityGroups: [albSecurityGroup.id],
      }],
      egress: [{
        protocol: "-1",
        fromPort: 0,
        toPort: 0,
        cidrBlocks: ["0.0.0.0/0"],
      }],
      tags: {
        Name: `${args.projectName}-ecs-sg`,
      },
    }, { parent: this });

    // ECS Cluster
    this.cluster = new aws.ecs.Cluster(`${name}-cluster`, {
      name: `${args.projectName}-cluster`,
      tags: {
        Name: `${args.projectName}-cluster`,
      },
    }, { parent: this });

    // IAM Role for ECS Task
    const taskRole = new aws.iam.Role(`${name}-task-role`, {
      assumeRolePolicy: JSON.stringify({
        Version: "2012-10-17",
        Statement: [{
          Action: "sts:AssumeRole",
          Effect: "Allow",
          Principal: {
            Service: "ecs-tasks.amazonaws.com",
          },
        }],
      }),
      tags: {
        Name: `${args.projectName}-task-role`,
      },
    }, { parent: this });

    const executionRole = new aws.iam.Role(`${name}-execution-role`, {
      assumeRolePolicy: JSON.stringify({
        Version: "2012-10-17",
        Statement: [{
          Action: "sts:AssumeRole",
          Effect: "Allow",
          Principal: {
            Service: "ecs-tasks.amazonaws.com",
          },
        }],
      }),
      managedPolicyArns: [
        "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
      ],
      tags: {
        Name: `${args.projectName}-execution-role`,
      },
    }, { parent: this });

    // Task Definition
    this.taskDefinition = new aws.ecs.TaskDefinition(`${name}-task`, {
      family: `${args.projectName}-task`,
      networkMode: "awsvpc",
      requiresCompatibilities: ["FARGATE"],
      cpu: "256",
      memory: "512",
      executionRoleArn: executionRole.arn,
      taskRoleArn: taskRole.arn,
      containerDefinitions: JSON.stringify([{
        name: args.projectName,
        image: args.imageUri,
        portMappings: [{
          containerPort: containerPort,
          protocol: "tcp",
        }],
        essential: true,
        logConfiguration: {
          logDriver: "awslogs",
          options: {
            "awslogs-group": `/ecs/${args.projectName}`,
            "awslogs-region": "us-east-1",
            "awslogs-stream-prefix": "ecs",
          },
        },
      }]),
      tags: {
        Name: `${args.projectName}-task`,
      },
    }, { parent: this });

    // CloudWatch Log Group
    new aws.cloudwatch.LogGroup(`${name}-logs`, {
      name: `/ecs/${args.projectName}`,
      retentionInDays: 7,
      tags: {
        Name: `${args.projectName}-logs`,
      },
    }, { parent: this });

    // Application Load Balancer
    this.loadBalancer = new aws.lb.LoadBalancer(`${name}-alb`, {
      name: `${args.projectName}-alb`,
      loadBalancerType: "application",
      subnets: [publicSubnet1.id, publicSubnet2.id],
      securityGroups: [albSecurityGroup.id],
      tags: {
        Name: `${args.projectName}-alb`,
      },
    }, { parent: this });

    // Target Group
    this.targetGroup = new aws.lb.TargetGroup(`${name}-tg`, {
      name: `${args.projectName}-tg`,
      port: containerPort,
      protocol: "HTTP",
      vpcId: vpc.id,
      targetType: "ip",
      healthCheck: {
        enabled: true,
        healthyThreshold: 2,
        interval: 30,
        matcher: "200",
        path: "/",
        port: "traffic-port",
        protocol: "HTTP",
        timeout: 5,
        unhealthyThreshold: 2,
      },
      tags: {
        Name: `${args.projectName}-tg`,
      },
    }, { parent: this });

    // ALB Listener
    new aws.lb.Listener(`${name}-listener`, {
      loadBalancerArn: this.loadBalancer.arn,
      port: "80",
      protocol: "HTTP",
      defaultActions: [{
        type: "forward",
        targetGroupArn: this.targetGroup.arn,
      }],
      tags: {
        Name: `${args.projectName}-listener`,
      },
    }, { parent: this });

    // ECS Service
    this.service = new aws.ecs.Service(`${name}-service`, {
      name: `${args.projectName}-service`,
      cluster: this.cluster.id,
      taskDefinition: this.taskDefinition.arn,
      desiredCount: 1,
      launchType: "FARGATE",
      networkConfiguration: {
        subnets: [publicSubnet1.id, publicSubnet2.id],
        securityGroups: [ecsSecurityGroup.id],
        assignPublicIp: true,
      },
      loadBalancers: [{
        targetGroupArn: this.targetGroup.arn,
        containerName: args.projectName,
        containerPort: containerPort,
      }],
      dependsOn: [this.loadBalancer],
      tags: {
        Name: `${args.projectName}-service`,
      },
    }, { parent: this });

    this.registerOutputs({
      clusterArn: this.cluster.arn,
      serviceArn: this.service.id,
      loadBalancerArn: this.loadBalancer.arn,
      loadBalancerDns: this.loadBalancer.dnsName,
    });
  }
}