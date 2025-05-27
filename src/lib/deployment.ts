import { exec } from 'child_process';
import { promisify } from 'util';
import AWS from 'aws-sdk';
import { ECSInfrastructure, ECSInfrastructureOutput } from '../../infrastructure';
import { deploymentManager } from './deploymentManager';
import { prisma } from './prisma';

const execAsync = promisify(exec);

export interface DeploymentConfig {
  projectId: string;
  projectName: string;
  gitRepoUrl: string;
  branch: string;
  commitSha: string;
}

export class DeploymentService {
  private region: string;
  private sts: AWS.STS;
  private deploymentLogs: Map<string, string[]> = new Map();

  constructor() {
    this.region = process.env.AWS_REGION || 'us-east-1';
    AWS.config.update({ region: this.region });
    this.sts = new AWS.STS();
  }

  private async logToDatabase(deploymentId: string, message: string) {
    try {
      const currentLogs = this.deploymentLogs.get(deploymentId) || [];
      currentLogs.push(`[${new Date().toISOString()}] ${message}`);
      this.deploymentLogs.set(deploymentId, currentLogs);

      // Update database with current logs
      await prisma.deployment.update({
        where: { id: deploymentId },
        data: { logs: currentLogs.join('\n') }
      });

      console.log(`[${deploymentId}] ${message}`);
    } catch (error) {
      console.error('Failed to log to database:', error);
    }
  }

  private async execWithLogging(command: string, projectId: string, deploymentId?: string): Promise<string> {
    if (deploymentId) {
      await this.logToDatabase(deploymentId, `Executing: ${command}`);
    }

    return new Promise((resolve, reject) => {
      const process = exec(command, (error, stdout, stderr) => {
        if (error) {
          if (deploymentId) {
            this.logToDatabase(deploymentId, `Error: ${error.message}`);
          }
          reject(error);
        } else {
          if (deploymentId && stdout.trim()) {
            this.logToDatabase(deploymentId, `Output: ${stdout.trim()}`);
          }
          resolve(stdout);
        }
      });

      // Real-time output logging
      if (deploymentId) {
        process.stdout?.on('data', (data) => {
          this.logToDatabase(deploymentId, `STDOUT: ${data.toString().trim()}`);
        });

        process.stderr?.on('data', (data) => {
          this.logToDatabase(deploymentId, `STDERR: ${data.toString().trim()}`);
        });
      }

      // Check for abort periodically
      const checkAborted = () => {
        if (deploymentManager.isAborted(projectId)) {
          process.kill('SIGTERM');
          if (deploymentId) {
            this.logToDatabase(deploymentId, 'Deployment aborted by user');
          }
          reject(new Error('Deployment aborted by user'));
          return;
        }
        setTimeout(checkAborted, 1000);
      };
      checkAborted();
    });
  }

  private async getECRRegistry(): Promise<string> {
    try {
      const identity = await this.sts.getCallerIdentity().promise();
      const accountId = identity.Account!;
      return `${accountId}.dkr.ecr.${this.region}.amazonaws.com`;
    } catch (error) {
      throw new Error(`Failed to get AWS account ID: ${error}`);
    }
  }

  private async ensureECRRepository(repositoryName: string): Promise<void> {
    const ecr = new AWS.ECR({ region: this.region });
    
    try {
      // Check if repository exists
      await ecr.describeRepositories({
        repositoryNames: [repositoryName]
      }).promise();
      
      console.log(`ECR repository ${repositoryName} already exists`);
    } catch (error) {
      // Repository doesn't exist, create it
      console.log(`Creating ECR repository: ${repositoryName}`);
      
      await ecr.createRepository({
        repositoryName,
        imageScanningConfiguration: {
          scanOnPush: true
        },
        encryptionConfiguration: {
          encryptionType: 'AES256'
        }
      }).promise();
      
      console.log(`Created ECR repository: ${repositoryName}`);
    }
  }

  async deployProject(config: DeploymentConfig, deploymentId?: string): Promise<ECSInfrastructureOutput> {
    let cloneDir: string | null = null;
    
    try {
      // Register deployment for tracking
      if (deploymentId) {
        deploymentManager.registerDeployment(config.projectId, deploymentId);
        await this.logToDatabase(deploymentId, '🚀 Starting deployment process...');
      }

      // Check if deployment was aborted before starting
      if (deploymentId && deploymentManager.isAborted(config.projectId)) {
        throw new Error('Deployment aborted by user');
      }

      // Step 1: Clone repository
      if (deploymentId) {
        await this.logToDatabase(deploymentId, '📥 Cloning repository...');
      }
      cloneDir = await this.cloneRepository(config.gitRepoUrl, config.branch, config.commitSha, config.projectId, deploymentId);

      // Check if deployment was aborted after cloning
      if (deploymentId && deploymentManager.isAborted(config.projectId)) {
        throw new Error('Deployment aborted by user');
      }

      // Step 2: Build and push Docker image
      if (deploymentId) {
        await this.logToDatabase(deploymentId, '🐳 Building and pushing Docker image...');
      }
      const imageUri = await this.buildAndPushImage(config.projectName, config.commitSha, cloneDir, config.projectId, deploymentId);

      // Check if deployment was aborted after building
      if (deploymentId && deploymentManager.isAborted(config.projectId)) {
        throw new Error('Deployment aborted by user');
      }

      // Step 3: Deploy infrastructure using AWS API
      if (deploymentId) {
        await this.logToDatabase(deploymentId, '☁️ Provisioning AWS infrastructure...');
      }
      const result = await this.deployInfrastructure(config.projectId, config.projectName, imageUri, deploymentId);

      // Mark deployment as completed
      if (deploymentId) {
        await this.logToDatabase(deploymentId, '✅ Deployment completed successfully!');
        deploymentManager.completeDeployment(config.projectId);
      }

      return result;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      console.error('Deployment failed:', error);
      
      if (deploymentId) {
        await this.logToDatabase(deploymentId, `❌ Deployment failed: ${errorMessage}`);
        deploymentManager.completeDeployment(config.projectId);
      }
      
      throw error;
    } finally {
      // Clean up clone directory
      if (cloneDir) {
        try {
          await execAsync(`rm -rf ${cloneDir}`);
          if (deploymentId) {
            await this.logToDatabase(deploymentId, '🧹 Cleaned up temporary files');
          }
          console.log(`Cleaned up clone directory: ${cloneDir}`);
        } catch (error) {
          console.warn(`Failed to clean up clone directory: ${error}`);
        }
      }
    }
  }

  private async cloneRepository(gitRepoUrl: string, branch: string, commitSha: string, projectId: string, deploymentId?: string): Promise<string> {
    const cloneDir = `/tmp/clone-${Date.now()}`;
    
    try {
      if (deploymentId) {
        await this.logToDatabase(deploymentId, `Cloning repository: ${gitRepoUrl}`);
      }

      // Get GitHub access token for the user
      const githubToken = await this.getGitHubToken(projectId);
      
      // Create authenticated clone URL
      const authenticatedUrl = await this.createAuthenticatedGitUrl(gitRepoUrl, githubToken);
      
      if (deploymentId) {
        await this.logToDatabase(deploymentId, 'Using GitHub authentication for private repository access');
      }
      
      await this.execWithLogging(`git clone -b ${branch} ${authenticatedUrl} ${cloneDir}`, projectId, deploymentId);
      
      if (deploymentId) {
        await this.logToDatabase(deploymentId, `Checked out branch: ${branch} (commit: ${commitSha})`);
      }
      
      // Check for Dockerfile
      if (deploymentId) {
        await this.logToDatabase(deploymentId, 'Checking for Dockerfile...');
      }
      try {
        await this.execWithLogging(`ls ${cloneDir}/Dockerfile`, projectId, deploymentId);
        if (deploymentId) {
          await this.logToDatabase(deploymentId, '✅ Found Dockerfile in repository');
        }
      } catch {
        throw new Error('Dockerfile not found in repository. Please add a Dockerfile to your project.');
      }
      
      return cloneDir;
    } catch (error) {
      // Clean up on error
      try {
        await execAsync(`rm -rf ${cloneDir}`);
      } catch {}
      throw new Error(`Failed to clone repository: ${error}`);
    }
  }

  private async getGitHubToken(projectId: string): Promise<string> {
    try {
      // Get the project to find the user
      const project = await prisma.project.findUnique({
        where: { id: projectId },
        include: {
          user: {
            include: {
              accounts: {
                where: {
                  provider: 'github'
                }
              }
            }
          }
        }
      });

      if (!project?.user?.accounts?.[0]?.access_token) {
        throw new Error('GitHub access token not found. Please reconnect your GitHub account.');
      }

      return project.user.accounts[0].access_token;
    } catch (error) {
      throw new Error(`Failed to get GitHub token: ${error}`);
    }
  }

  private async createAuthenticatedGitUrl(gitRepoUrl: string, token: string): Promise<string> {
    // Convert GitHub HTTPS URL to authenticated format
    // From: https://github.com/user/repo.git
    // To: https://token@github.com/user/repo.git
    
    if (!gitRepoUrl.includes('github.com')) {
      throw new Error('Only GitHub repositories are currently supported');
    }

    // Handle both .git and non-.git URLs
    const cleanUrl = gitRepoUrl.replace('https://github.com/', '').replace('.git', '');
    return `https://${token}@github.com/${cleanUrl}.git`;
  }

  private async buildAndPushImage(projectName: string, commitSha: string, cloneDir: string, projectId: string, deploymentId?: string): Promise<string> {
    const ecrRegistry = await this.getECRRegistry();
    const repositoryName = projectName.toLowerCase().replace(/[^a-z0-9-_]/g, '-');
    const imageTag = `${repositoryName}:${commitSha}`;
    const imageUri = `${ecrRegistry}/${imageTag}`;

    try {
      // Ensure ECR repository exists
      if (deploymentId) {
        await this.logToDatabase(deploymentId, `Ensuring ECR repository exists: ${repositoryName}`);
      }
      await this.ensureECRRepository(repositoryName);

      // Start CodeBuild project to build and push image
      if (deploymentId) {
        await this.logToDatabase(deploymentId, 'Starting CodeBuild project for container build...');
      }
      
      const buildId = await this.startCodeBuild(projectName, repositoryName, commitSha, cloneDir, deploymentId);
      
      if (deploymentId) {
        await this.logToDatabase(deploymentId, `CodeBuild started: ${buildId}`);
      }

      // Wait for build to complete
      await this.waitForCodeBuildCompletion(buildId, deploymentId);

      if (deploymentId) {
        await this.logToDatabase(deploymentId, `✅ Successfully built and pushed image: ${imageUri}`);
      }
      return imageUri;
    } catch (error) {
      throw new Error(`Failed to build/push image: ${error}`);
    }
  }


  private async startCodeBuild(projectName: string, repositoryName: string, commitSha: string, cloneDir: string, deploymentId?: string): Promise<string> {
    const codebuild = new AWS.CodeBuild({ region: this.region });
    
    // Upload source to S3 first
    const sourceLocation = await this.uploadSourceToS3(cloneDir, projectName, commitSha);
    
    const buildProjectName = `${projectName.toLowerCase().replace(/[^a-z0-9-]/g, '-')}-build`;
    
    // Create buildspec content
    const buildspec = `version: 0.2
phases:
  pre_build:
    commands:
      - echo Logging in to Amazon ECR...
      - aws ecr get-login-password --region ${this.region} | docker login --username AWS --password-stdin ${await this.getECRRegistry()}
  build:
    commands:
      - echo Build started on \`date\`
      - echo Building the Docker image...
      - docker build -t ${repositoryName}:${commitSha} .
      - docker tag ${repositoryName}:${commitSha} ${await this.getECRRegistry()}/${repositoryName}:${commitSha}
  post_build:
    commands:
      - echo Build completed on \`date\`
      - echo Pushing the Docker image...
      - docker push ${await this.getECRRegistry()}/${repositoryName}:${commitSha}`;

    const logGroupName = `/aws/codebuild/${buildProjectName}`
    
    // Ensure CloudWatch log group exists
    const cloudwatchLogs = new AWS.CloudWatchLogs({ region: this.region })
    try {
      await cloudwatchLogs.createLogGroup({
        logGroupName: logGroupName
      }).promise()
      
      if (deploymentId) {
        await this.logToDatabase(deploymentId, `Created CloudWatch log group: ${logGroupName}`)
      }
    } catch (error: any) {
      if (error.code !== 'ResourceAlreadyExistsException') {
        console.warn('Failed to create log group:', error)
      }
    }
    
    const params = {
      name: buildProjectName,
      source: {
        type: 'S3',
        location: sourceLocation,
        buildspec: buildspec
      },
      artifacts: {
        type: 'NO_ARTIFACTS'
      },
      environment: {
        type: 'LINUX_CONTAINER',
        image: 'aws/codebuild/amazonlinux2-x86_64-standard:4.0',
        computeType: 'BUILD_GENERAL1_SMALL',
        privilegedMode: true
      },
      logsConfig: {
        cloudWatchLogs: {
          status: 'ENABLED',
          groupName: logGroupName
        }
      },
      serviceRole: await this.getCodeBuildRole()
    };

    // Create or update CodeBuild project
    try {
      await codebuild.createProject(params).promise();
      if (deploymentId) {
        await this.logToDatabase(deploymentId, `Created CodeBuild project: ${buildProjectName}`);
      }
    } catch (error: any) {
      if (error.code === 'ResourceAlreadyExistsException') {
        // Update existing project
        await codebuild.updateProject(params).promise();
        if (deploymentId) {
          await this.logToDatabase(deploymentId, `Updated CodeBuild project: ${buildProjectName}`);
        }
      } else {
        throw error;
      }
    }

    // Start build
    const result = await codebuild.startBuild({
      projectName: buildProjectName
    }).promise();
    
    return result.build!.id!;
  }

  private async waitForCodeBuildCompletion(buildId: string, deploymentId?: string): Promise<void> {
    const codebuild = new AWS.CodeBuild({ region: this.region });
    const cloudwatchLogs = new AWS.CloudWatchLogs({ region: this.region });
    
    let logGroupName: string | undefined;
    let logStreamName: string | undefined;
    let nextToken: string | undefined;
    let logStreamFound = false;
    
    while (true) {
      const result = await codebuild.batchGetBuilds({
        ids: [buildId]
      }).promise();

      const build = result.builds![0];
      const status = build.buildStatus;

      // Get log info if available
      if (build.logs?.cloudWatchLogs?.groupName && !logStreamFound) {
        logGroupName = build.logs.cloudWatchLogs.groupName;
        logStreamName = build.logs.cloudWatchLogs.streamName;
        
        if (deploymentId) {
          await this.logToDatabase(deploymentId, `📋 CodeBuild reports log group: ${logGroupName}, stream: ${logStreamName || 'undefined'}`);
        }
        
        // Only mark as found if we have both group and stream
        if (logGroupName && logStreamName) {
          logStreamFound = true;
          if (deploymentId) {
            await this.logToDatabase(deploymentId, `✅ Log streaming ready: ${logGroupName}/${logStreamName}`);
          }
        }
      }

      // If we don't have log stream info yet, try to find it by listing streams
      if (!logStreamFound && logGroupName && deploymentId) {
        try {
          if (deploymentId) {
            await this.logToDatabase(deploymentId, `🔍 Searching for log streams in ${logGroupName}...`);
          }
          
          const streams = await cloudwatchLogs.describeLogStreams({
            logGroupName: logGroupName,
            orderBy: 'LastEventTime',
            descending: true,
            limit: 10
          }).promise();

          if (deploymentId) {
            await this.logToDatabase(deploymentId, `Found ${streams.logStreams?.length || 0} log streams`);
          }

          if (streams.logStreams && streams.logStreams.length > 0) {
            // Try multiple strategies to find the right stream
            let matchingStream = null;
            
            // Strategy 1: Find stream that contains the full build ID
            matchingStream = streams.logStreams.find(stream => 
              stream.logStreamName?.includes(buildId)
            );
            
            // Strategy 2: Find stream that contains part of the build ID
            if (!matchingStream) {
              const buildIdShort = buildId.split(':').pop()?.split('-').slice(0, 2).join('-');
              matchingStream = streams.logStreams.find(stream => 
                buildIdShort && stream.logStreamName?.includes(buildIdShort)
              );
            }
            
            // Strategy 3: Use the most recent stream (fallback)
            if (!matchingStream) {
              matchingStream = streams.logStreams[0];
              if (deploymentId) {
                await this.logToDatabase(deploymentId, `Using most recent log stream as fallback`);
              }
            }
            
            if (matchingStream) {
              logStreamName = matchingStream.logStreamName;
              logStreamFound = true;
              
              if (deploymentId) {
                await this.logToDatabase(deploymentId, `✅ Found log stream: ${logStreamName}`);
              }
            }
          }
        } catch (error: any) {
          if (deploymentId) {
            await this.logToDatabase(deploymentId, `Error searching log streams: ${error.message}`);
          }
        }
      }

      // Stream logs if available
      if (logGroupName && logStreamName && deploymentId) {
        try {
          const logsResult = await cloudwatchLogs.getLogEvents({
            logGroupName,
            logStreamName,
            nextToken,
            startFromHead: true
          }).promise();

          for (const event of logsResult.events || []) {
            if (event.message && event.message.trim()) {
              await this.logToDatabase(deploymentId, `🔨 ${event.message.trim()}`);
            }
          }

          nextToken = logsResult.nextForwardToken;
        } catch (error: any) {
          if (deploymentId) {
            await this.logToDatabase(deploymentId, `Log streaming error: ${error.message}`);
          }
          console.warn('Failed to stream logs:', error);
        }
      } else if (deploymentId && status === 'IN_PROGRESS' && !logStreamFound) {
        await this.logToDatabase(deploymentId, `🔍 Searching for CodeBuild logs...`);
      }

      if (deploymentId) {
        await this.logToDatabase(deploymentId, `CodeBuild status: ${status}`);
      }

      if (status === 'SUCCEEDED') {
        // Get final logs
        if (logGroupName && logStreamName && deploymentId) {
          try {
            const finalLogs = await cloudwatchLogs.getLogEvents({
              logGroupName,
              logStreamName,
              nextToken,
              startFromHead: true
            }).promise();

            for (const event of finalLogs.events || []) {
              if (event.message) {
                await this.logToDatabase(deploymentId, `🔨 ${event.message.trim()}`);
              }
            }
          } catch (error) {
            console.warn('Failed to get final logs:', error);
          }
        }
        return;
      } else if (status === 'FAILED' || status === 'FAULT' || status === 'STOPPED' || status === 'TIMED_OUT') {
        if (logGroupName && deploymentId) {
          await this.logToDatabase(deploymentId, `❌ CodeBuild logs available in CloudWatch: ${logGroupName}`);
        }
        throw new Error(`CodeBuild failed with status: ${status}`);
      }

      // Wait 5 seconds before checking again (shorter for better log streaming)
      await new Promise(resolve => setTimeout(resolve, 5000));
    }
  }

  private async uploadSourceToS3(cloneDir: string, projectName: string, commitSha: string): Promise<string> {
    const s3 = new AWS.S3({ region: this.region });
    const bucketName = `${projectName.toLowerCase().replace(/[^a-z0-9-]/g, '-')}-builds-${this.region}`;
    const keyName = `source/${commitSha}.zip`;

    // Create bucket if it doesn't exist
    try {
      await s3.createBucket({
        Bucket: bucketName,
        CreateBucketConfiguration: this.region === 'us-east-1' ? undefined : { LocationConstraint: this.region }
      }).promise();
    } catch (error: any) {
      if (error.code !== 'BucketAlreadyOwnedByYou' && error.code !== 'BucketAlreadyExists') {
        throw error;
      }
    }

    // Create zip of source code
    await this.execWithLogging(`cd ${cloneDir} && zip -r /tmp/${commitSha}.zip . -x "*.git*"`, '', undefined);

    // Upload to S3
    const fileContent = require('fs').readFileSync(`/tmp/${commitSha}.zip`);
    await s3.upload({
      Bucket: bucketName,
      Key: keyName,
      Body: fileContent
    }).promise();

    // Clean up local zip
    await this.execWithLogging(`rm -f /tmp/${commitSha}.zip`, '', undefined);

    return `${bucketName}/${keyName}`;
  }

  private async getCodeBuildRole(): Promise<string> {
    // Return a pre-created CodeBuild service role ARN
    // This role needs permissions for ECR, S3, and CloudWatch Logs
    const accountId = (await this.sts.getCallerIdentity().promise()).Account!;
    return `arn:aws:iam::${accountId}:role/CodeBuildServiceRole`;
  }

  private async deployInfrastructure(projectId: string, projectName: string, imageUri: string, deploymentId?: string): Promise<ECSInfrastructureOutput> {
    // Fetch environment variables for the project
    const environmentVariables = await this.getEnvironmentVariables(projectId);

    if (deploymentId && environmentVariables.length > 0) {
      await this.logToDatabase(deploymentId, `📋 Found ${environmentVariables.length} environment variables`);
    }

    // Fetch project to get network configuration
    const project = await this.getProjectNetworkConfig(projectId);
    
    const infrastructureArgs: any = {
      projectName,
      imageUri,
      containerPort: 3000,
      region: this.region,
      environmentVariables,
      cpu: project.cpu,
      memory: project.memory,
      diskSize: project.diskSize,
    };

    // Add existing network resources if configured
    if (project.existingVpcId) {
      infrastructureArgs.existingVpcId = project.existingVpcId;
      if (deploymentId) {
        await this.logToDatabase(deploymentId, `🌐 Using existing VPC: ${project.existingVpcId}`);
      }
    }

    if (project.existingSubnetIds) {
      try {
        infrastructureArgs.existingSubnetIds = JSON.parse(project.existingSubnetIds);
        if (deploymentId) {
          await this.logToDatabase(deploymentId, `🌐 Using existing subnets: ${infrastructureArgs.existingSubnetIds.join(', ')}`);
        }
      } catch (error) {
        console.warn('Failed to parse existing subnet IDs:', error);
      }
    }

    if (project.existingClusterArn) {
      infrastructureArgs.existingClusterArn = project.existingClusterArn;
      if (deploymentId) {
        await this.logToDatabase(deploymentId, `🚀 Using existing ECS cluster: ${project.existingClusterArn}`);
      }
    }

    const infrastructure = new ECSInfrastructure(infrastructureArgs);

    if (deploymentId) {
      await this.logToDatabase(deploymentId, 'Creating/updating AWS infrastructure...');
      await this.logToDatabase(deploymentId, `- Resource allocation: ${project.cpu} CPU units, ${project.memory} MB memory, ${project.diskSize} GB disk`);
      await this.logToDatabase(deploymentId, '- Setting up VPC and networking');
      await this.logToDatabase(deploymentId, '- Creating security groups');
      await this.logToDatabase(deploymentId, '- Setting up ECS cluster and service');
      await this.logToDatabase(deploymentId, '- Configuring load balancer');
      if (environmentVariables.length > 0) {
        await this.logToDatabase(deploymentId, `- Configuring ${environmentVariables.length} environment variables and secrets`);
      }
    }

    const result = await infrastructure.createOrUpdateInfrastructure();
    
    if (deploymentId) {
      await this.logToDatabase(deploymentId, `✅ Infrastructure ready!`);
      await this.logToDatabase(deploymentId, `- ECS Service: ${result.serviceArn}`);
      await this.logToDatabase(deploymentId, `- Load Balancer: ${result.loadBalancerDns}`);
    }

    return result;
  }

  private async getEnvironmentVariables(projectId: string) {
    try {
      const envVars = await prisma.environmentVariable.findMany({
        where: {
          projectId
        }
      });

      return envVars.map(envVar => ({
        key: envVar.key,
        value: envVar.value || undefined,
        isSecret: envVar.isSecret,
        secretKey: envVar.secretKey || undefined
      }));
    } catch (error) {
      console.error('Error fetching environment variables:', error);
      return [];
    }
  }

  private async getProjectNetworkConfig(projectId: string) {
    try {
      const project = await prisma.project.findUnique({
        where: { id: projectId },
        select: {
          existingVpcId: true,
          existingSubnetIds: true,
          existingClusterArn: true,
          cpu: true,
          memory: true,
          diskSize: true
        }
      });

      return project || {
        existingVpcId: null,
        existingSubnetIds: null,
        existingClusterArn: null,
        cpu: 256,
        memory: 512,
        diskSize: 20
      };
    } catch (error) {
      console.error('Error fetching project configuration:', error);
      return {
        existingVpcId: null,
        existingSubnetIds: null,
        existingClusterArn: null,
        cpu: 256,
        memory: 512,
        diskSize: 20
      };
    }
  }
}