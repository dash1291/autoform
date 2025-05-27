import * as AWS from 'aws-sdk';

export interface IAMServiceConfig {
  projectName: string;
  region?: string;
}

export class IAMService {
  private iam: AWS.IAM;
  private sts: AWS.STS;
  private projectName: string;
  private region: string;
  
  public executionRoleArn: string;
  public taskRoleArn: string;
  public codeBuildRoleArn: string;

  constructor(private config: IAMServiceConfig) {
    this.projectName = config.projectName;
    this.region = config.region || 'us-east-1';
    
    AWS.config.update({ region: this.region });
    this.iam = new AWS.IAM();
    this.sts = new AWS.STS();
  }

  async initialize(): Promise<void> {
    // Create IAM roles
    this.taskRoleArn = await this.createOrUpdateTaskRole();
    this.executionRoleArn = await this.createOrUpdateExecutionRole();
    this.codeBuildRoleArn = await this.createOrUpdateCodeBuildRole();
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

  private async createOrUpdateCodeBuildRole(): Promise<string> {
    const roleName = `${this.projectName}-codebuild-role`;
    
    try {
      // Check if role already exists
      const role = await this.iam.getRole({ RoleName: roleName }).promise();
      console.log(`Found existing CodeBuild role: ${roleName}`);
      return role.Role.Arn!;
    } catch (error: any) {
      if (error.code === 'NoSuchEntity') {
        console.log(`Creating new CodeBuild role: ${roleName}`);
        
        const assumeRolePolicy = {
          Version: '2012-10-17',
          Statement: [
            {
              Action: 'sts:AssumeRole',
              Effect: 'Allow',
              Principal: {
                Service: 'codebuild.amazonaws.com',
              },
            },
          ],
        };

        const inlinePolicy = {
          Version: '2012-10-17',
          Statement: [
            {
              Effect: 'Allow',
              Action: [
                'logs:CreateLogGroup',
                'logs:CreateLogStream',
                'logs:PutLogEvents',
              ],
              Resource: 'arn:aws:logs:*:*:*',
            },
            {
              Effect: 'Allow',
              Action: [
                'ecr:BatchCheckLayerAvailability',
                'ecr:GetDownloadUrlForLayer',
                'ecr:BatchGetImage',
                'ecr:GetAuthorizationToken',
              ],
              Resource: '*',
            },
            {
              Effect: 'Allow',
              Action: [
                'ecs:UpdateService',
                'ecs:DescribeServices',
                'ecs:DescribeTaskDefinition',
                'ecs:RegisterTaskDefinition',
              ],
              Resource: '*',
            },
            {
              Effect: 'Allow',
              Action: ['iam:PassRole'],
              Resource: '*',
            },
          ],
        };

        const role = await this.iam.createRole({
          RoleName: roleName,
          AssumeRolePolicyDocument: JSON.stringify(assumeRolePolicy),
          InlinePolicies: [
            {
              PolicyName: `${this.projectName}-codebuild-policy`,
              PolicyDocument: JSON.stringify(inlinePolicy),
            },
          ],
          Tags: [{ Key: 'Name', Value: roleName }]
        }).promise();

        // Attach managed policy
        await this.iam.attachRolePolicy({
          RoleName: roleName,
          PolicyArn: 'arn:aws:iam::aws:policy/AWSCodeBuildDeveloperAccess'
        }).promise();

        console.log(`Created CodeBuild role: ${role.Role.Arn}`);
        return role.Role.Arn!;
      } else {
        throw error;
      }
    }
  }

  private async getAccountId(): Promise<string> {
    const identity = await this.sts.getCallerIdentity().promise();
    return identity.Account!;
  }
}