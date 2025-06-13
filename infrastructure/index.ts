import * as AWS from 'aws-sdk';
import { ECSInfrastructureArgs, ECSInfrastructureOutput, EnvironmentVariable } from './types';

export { ECSInfrastructureArgs, ECSInfrastructureOutput, EnvironmentVariable };
import { VPCService } from './services/vpc-service';
import { IAMService } from './services/iam-service';
import { LoadBalancerService } from './services/load-balancer-service';
import { ECSService } from './services/ecs-service';

export class ECSInfrastructure {
  private logs: AWS.CloudWatchLogs;
  private projectName: string;
  private imageUri: string;
  private containerPort: number;
  private args: ECSInfrastructureArgs;
  private region: string;
  private cpu: number;
  private memory: number;
  private diskSize: number;

  private vpcService!: VPCService;
  private iamService!: IAMService;
  private loadBalancerService!: LoadBalancerService;
  private ecsService!: ECSService;

  constructor(args: ECSInfrastructureArgs) {
    this.region = args.region || 'us-east-1';
    AWS.config.update({ region: this.region });

    this.logs = new AWS.CloudWatchLogs();
    this.projectName = args.projectName;
    this.imageUri = args.imageUri;
    this.containerPort = args.containerPort || 3000;
    this.cpu = args.cpu || 256;
    this.memory = args.memory || 512;
    this.diskSize = args.diskSize || 21;
    this.args = args;
  }

  async createOrUpdateInfrastructure(): Promise<ECSInfrastructureOutput> {
    try {
      console.log('Starting infrastructure setup...');

      // Initialize VPC service
      this.vpcService = new VPCService({
        projectName: this.projectName,
        environmentVariables: this.args.environmentVariables || [],
        region: this.region,
        existingVpcId: this.args.existingVpcId,
        existingSubnetIds: this.args.existingSubnetIds
      });
      await this.vpcService.initialize();

      // Initialize IAM service
      this.iamService = new IAMService({
        projectName: this.projectName,
        region: this.region
      });
      await this.iamService.initialize();

      // CloudWatch log group - Ensure it exists
      await this.createOrUpdateLogGroup();

      // Initialize load balancer service
      this.loadBalancerService = new LoadBalancerService({
        projectName: this.projectName,
        region: this.region,
        vpcId: this.vpcService.vpcId,
        subnetIds: this.vpcService.subnetIds,
        securityGroupId: this.vpcService.securityGroupIds.albSecurityGroupId,
        containerPort: this.containerPort,
        healthCheckPath: this.args.healthCheckPath
      });
      await this.loadBalancerService.initialize();

      // Initialize ECS service
      this.ecsService = new ECSService({
        projectName: this.projectName,
        environmentVariables: this.args.environmentVariables || [],
        cpu: this.cpu,
        memory: this.memory,
        diskSize: this.diskSize,
        imageUri: this.imageUri,
        containerPort: this.containerPort,
        region: this.region,
        existingClusterArn: this.args.existingClusterArn,
        vpcId: this.vpcService.vpcId,
        subnetIds: this.vpcService.subnetIds,
        securityGroupId: this.vpcService.securityGroupIds.ecsSecurityGroupId,
        executionRoleArn: this.iamService.executionRoleArn,
        taskRoleArn: this.iamService.taskRoleArn,
        targetGroupArn: this.loadBalancerService.targetGroupArn
      });
      await this.ecsService.initialize();

      console.log('✅ Infrastructure setup complete!');

      return {
        clusterArn: this.ecsService.clusterArn,
        serviceArn: this.ecsService.serviceArn,
        loadBalancerArn: this.loadBalancerService.loadBalancerArn,
        loadBalancerDns: this.loadBalancerService.loadBalancerDns,
      };
    } catch (error) {
      console.error('Error creating/updating infrastructure:', error);
      throw error;
    }
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

  async destroyInfrastructure(): Promise<void> {
    console.log('Infrastructure destruction would need to be implemented');
  }
}