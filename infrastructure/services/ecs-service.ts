import * as AWS from 'aws-sdk';
import { EnvironmentVariable } from "../types";

export interface ECSServiceConfig {
  projectName: string;
  environmentVariables: EnvironmentVariable[];
  cpu: number;
  memory: number;
  diskSize: number;
  imageUri: string;
  containerPort?: number;
  region?: string;
  existingClusterArn?: string;
  vpcId: string;
  subnetIds: string[];
  securityGroupId: string;
  executionRoleArn: string;
  taskRoleArn: string;
  targetGroupArn: string;
}

export class ECSService {
  private ecs: AWS.ECS;
  private secretsManager: AWS.SecretsManager;
  private sts: AWS.STS;
  private projectName: string;
  private region: string;
  private containerPort: number;
  
  public clusterArn: string;
  public serviceArn: string;
  public taskDefinitionArn: string;

  constructor(private config: ECSServiceConfig) {
    this.projectName = config.projectName;
    this.region = config.region || 'us-east-1';
    this.containerPort = config.containerPort || 3000;
    
    AWS.config.update({ region: this.region });
    this.ecs = new AWS.ECS();
    this.secretsManager = new AWS.SecretsManager();
    this.sts = new AWS.STS();
  }

  async initialize(): Promise<void> {
    // Set up or find ECS cluster
    this.clusterArn = await this.createOrFindCluster();
    
    // Create task definition
    this.taskDefinitionArn = await this.createTaskDefinition();
    
    // Create or update ECS service
    this.serviceArn = await this.createOrUpdateService();
  }

  private async createOrFindCluster(): Promise<string> {
    if (this.config.existingClusterArn) {
      console.log(`Using existing cluster: ${this.config.existingClusterArn}`);
      return this.config.existingClusterArn;
    }

    try {
      // Check if cluster exists
      const clusters = await this.ecs.describeClusters({
        clusters: [`${this.projectName}-cluster`]
      }).promise();

      if (clusters.clusters && clusters.clusters.length > 0) {
        const cluster = clusters.clusters[0];
        if (cluster.clusterName && cluster.status === 'ACTIVE') {
          console.log(`Found existing ECS cluster: ${cluster.clusterArn}`);
          return cluster.clusterArn!;
        }
      }
      
      console.log('No existing ECS cluster found, creating new one');
    } catch (error) {
      console.log('Error checking for existing cluster, creating new one:', error);
    }

    // Create new cluster
    const result = await this.ecs.createCluster({
      clusterName: `${this.projectName}-cluster`,
      tags: [{ key: 'Name', value: `${this.projectName}-cluster` }]
    }).promise();
    
    console.log(`Created ECS cluster: ${result.cluster?.clusterArn}`);
    return result.cluster!.clusterArn!;
  }

  private async createTaskDefinition(): Promise<string> {
    // Prepare environment variables and secrets
    const environment: AWS.ECS.KeyValuePair[] = [];
    const secrets: AWS.ECS.Secret[] = [];

    if (this.config.environmentVariables) {
      for (const envVar of this.config.environmentVariables) {
        if (envVar.isSecret && envVar.secretKey) {
          // Add to secrets array for AWS Secrets Manager
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
      image: this.config.imageUri,
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

    const result = await this.ecs.registerTaskDefinition({
      family: `${this.projectName}-task`,
      networkMode: 'awsvpc',
      requiresCompatibilities: ['FARGATE'],
      cpu: this.config.cpu.toString(),
      memory: this.config.memory.toString(),
      ephemeralStorage: {
        sizeInGiB: this.config.diskSize
      },
      executionRoleArn: this.config.executionRoleArn,
      taskRoleArn: this.config.taskRoleArn,
      containerDefinitions: [containerDef],
      tags: [{ key: 'Name', value: `${this.projectName}-task` }]
    }).promise();

    console.log(`Created task definition: ${result.taskDefinition!.taskDefinitionArn}`);
    return result.taskDefinition!.taskDefinitionArn!;
  }

  private async createOrUpdateService(): Promise<string> {
    const serviceName = `${this.projectName}-service`;
    
    try {
      // Check if service already exists
      const existingServices = await this.ecs.describeServices({
        cluster: this.clusterArn,
        services: [serviceName]
      }).promise();
      
      if (existingServices.services && existingServices.services.length > 0) {
        const existingService = existingServices.services[0];
        
        if (existingService.status === 'ACTIVE') {
          console.log(`Updating existing ECS service: ${existingService.serviceArn}`);
          
          // Update the service with new task definition
          const updateResponse = await this.ecs.updateService({
            cluster: this.clusterArn,
            service: serviceName,
            taskDefinition: this.taskDefinitionArn,
            desiredCount: 1,
            enableExecuteCommand: true
          }).promise();
          
          console.log('Service updated successfully');
          return updateResponse.service!.serviceArn!;
        }
      }
    } catch (error) {
      console.log('No existing service found or error checking, creating new service');
    }
    
    // Create new service
    const serviceResponse = await this.ecs.createService({
      serviceName: serviceName,
      cluster: this.clusterArn,
      taskDefinition: this.taskDefinitionArn,
      desiredCount: 1,
      launchType: 'FARGATE',
      enableExecuteCommand: true,
      networkConfiguration: {
        awsvpcConfiguration: {
          subnets: this.config.subnetIds,
          securityGroups: [this.config.securityGroupId],
          assignPublicIp: 'ENABLED'
        }
      },
      loadBalancers: [{
        targetGroupArn: this.config.targetGroupArn,
        containerName: this.projectName,
        containerPort: this.containerPort
      }],
      tags: [{ key: 'Name', value: `${this.projectName}-service` }]
    }).promise();

    console.log(`ECS service created: ${serviceResponse.service?.serviceArn}`);
    return serviceResponse.service!.serviceArn!;
  }

  private async getAccountId(): Promise<string> {
    const identity = await this.sts.getCallerIdentity().promise();
    return identity.Account!;
  }

  private async getSecretArn(secretName: string): Promise<string> {
    try {
      const result = await this.secretsManager.describeSecret({
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
}