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
  healthCheckPath?: string;
  region?: string;
  existingVpcId?: string;
  existingSubnetIds?: string[];
  existingClusterArn?: string;
  environmentVariables?: EnvironmentVariable[];
  cpu?: number;
  memory?: number;
  diskSize?: number;
}

export interface ECSInfrastructureOutput {
  clusterArn: string;
  serviceArn: string;
  loadBalancerArn: string;
  loadBalancerDns: string;
}

export interface ExistingResources {
  vpc: AWS.EC2.Vpc | null;
  subnets: AWS.EC2.Subnet[];
  cluster: AWS.ECS.Cluster | null;
  loadBalancer: AWS.ELBv2.LoadBalancer | null;
}

export interface SecurityGroupIds {
  albSecurityGroupId: string;
  ecsSecurityGroupId: string;
}

export interface IAMRoles {
  taskRoleArn: string;
  executionRoleArn: string;
}