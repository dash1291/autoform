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
      const result = await this.deployInfrastructure(config.projectName, imageUri, deploymentId);

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

      // Ensure Docker buildx is available for cross-platform builds
      if (deploymentId) {
        await this.logToDatabase(deploymentId, 'Setting up Docker buildx for cross-platform builds...');
      }
      try {
        await this.execWithLogging('docker buildx version', projectId, deploymentId);
      } catch (error) {
        if (deploymentId) {
          await this.logToDatabase(deploymentId, 'Docker buildx not available, using regular docker build');
        }
      }

      // Build image for AMD64 platform (required for ECS Fargate)
      if (deploymentId) {
        await this.logToDatabase(deploymentId, `Building Docker image: ${imageTag} for linux/amd64 platform`);
      }
      await this.execWithLogging(`cd ${cloneDir} && docker build --platform linux/amd64 -t ${imageTag} .`, projectId, deploymentId);

      // Tag for ECR
      if (deploymentId) {
        await this.logToDatabase(deploymentId, `Tagging image for ECR: ${imageUri}`);
      }
      await this.execWithLogging(`docker tag ${imageTag} ${imageUri}`, projectId, deploymentId);

      // Login to ECR
      if (deploymentId) {
        await this.logToDatabase(deploymentId, 'Logging into ECR...');
      }
      await this.execWithLogging(`aws ecr get-login-password --region ${this.region} | docker login --username AWS --password-stdin ${ecrRegistry}`, projectId, deploymentId);

      // Push to ECR
      if (deploymentId) {
        await this.logToDatabase(deploymentId, `Pushing image to ECR: ${imageUri}`);
      }
      await this.execWithLogging(`docker push ${imageUri}`, projectId, deploymentId);

      if (deploymentId) {
        await this.logToDatabase(deploymentId, `✅ Successfully pushed image: ${imageUri}`);
      }
      return imageUri;
    } catch (error) {
      throw new Error(`Failed to build/push image: ${error}`);
    }
  }

  private async deployInfrastructure(projectName: string, imageUri: string, deploymentId?: string): Promise<ECSInfrastructureOutput> {
    const infrastructure = new ECSInfrastructure({
      projectName,
      imageUri,
      containerPort: 3000,
      region: this.region,
    });

    if (deploymentId) {
      await this.logToDatabase(deploymentId, 'Creating/updating AWS infrastructure...');
      await this.logToDatabase(deploymentId, '- Setting up VPC and networking');
      await this.logToDatabase(deploymentId, '- Creating security groups');
      await this.logToDatabase(deploymentId, '- Setting up ECS cluster and service');
      await this.logToDatabase(deploymentId, '- Configuring load balancer');
    }

    const result = await infrastructure.createOrUpdateInfrastructure();
    
    if (deploymentId) {
      await this.logToDatabase(deploymentId, `✅ Infrastructure ready!`);
      await this.logToDatabase(deploymentId, `- ECS Service: ${result.serviceArn}`);
      await this.logToDatabase(deploymentId, `- Load Balancer: ${result.loadBalancerDns}`);
    }

    return result;
  }
}