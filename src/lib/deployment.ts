import { exec } from 'child_process';
import { promisify } from 'util';
import * as pulumi from '@pulumi/pulumi';
import { ECSInfrastructure } from '../../infrastructure';

const execAsync = promisify(exec);

export interface DeploymentConfig {
  projectId: string;
  projectName: string;
  gitRepoUrl: string;
  commitSha: string;
}

export class DeploymentService {
  private ecrRegistry: string;

  constructor() {
    this.ecrRegistry = process.env.ECR_REGISTRY || '';
  }

  async deployProject(config: DeploymentConfig): Promise<void> {
    try {
      // Step 1: Clone repository
      await this.cloneRepository(config.gitRepoUrl, config.commitSha);

      // Step 2: Build and push Docker image
      const imageUri = await this.buildAndPushImage(config.projectName, config.commitSha);

      // Step 3: Deploy infrastructure using Pulumi
      await this.deployInfrastructure(config.projectName, imageUri);

    } catch (error) {
      console.error('Deployment failed:', error);
      throw error;
    }
  }

  private async cloneRepository(gitRepoUrl: string, commitSha: string): Promise<void> {
    const cloneDir = `/tmp/clone-${Date.now()}`;
    
    try {
      await execAsync(`git clone ${gitRepoUrl} ${cloneDir}`);
      await execAsync(`cd ${cloneDir} && git checkout ${commitSha}`);
      
      // Check for Dockerfile
      try {
        await execAsync(`ls ${cloneDir}/Dockerfile`);
      } catch {
        // Create a default Dockerfile for Node.js projects
        await this.createDefaultDockerfile(cloneDir);
      }
    } catch (error) {
      throw new Error(`Failed to clone repository: ${error}`);
    }
  }

  private async createDefaultDockerfile(projectDir: string): Promise<void> {
    const dockerfile = `
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY . .

EXPOSE 3000

CMD ["npm", "start"]
`;

    await execAsync(`echo '${dockerfile}' > ${projectDir}/Dockerfile`);
  }

  private async buildAndPushImage(projectName: string, commitSha: string): Promise<string> {
    const imageTag = `${projectName}:${commitSha}`;
    const imageUri = `${this.ecrRegistry}/${imageTag}`;
    const cloneDir = `/tmp/clone-${Date.now()}`;

    try {
      // Build image
      await execAsync(`cd ${cloneDir} && docker build -t ${imageTag} .`);

      // Tag for ECR
      await execAsync(`docker tag ${imageTag} ${imageUri}`);

      // Push to ECR
      await execAsync(`aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ${this.ecrRegistry}`);
      await execAsync(`docker push ${imageUri}`);

      return imageUri;
    } catch (error) {
      throw new Error(`Failed to build/push image: ${error}`);
    }
  }

  private async deployInfrastructure(projectName: string, imageUri: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const program = async () => {
        const infrastructure = new ECSInfrastructure(`${projectName}-infra`, {
          projectName,
          imageUri,
          containerPort: 3000,
        });

        return {
          clusterArn: infrastructure.cluster.arn,
          serviceArn: infrastructure.service.id,
          loadBalancerArn: infrastructure.loadBalancer.arn,
          loadBalancerDns: infrastructure.loadBalancer.dnsName,
        };
      };

      pulumi.runtime.run(program)
        .then(() => resolve())
        .catch(reject);
    });
  }
}