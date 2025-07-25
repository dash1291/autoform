export interface User {
  id: string
  email: string
  name?: string
  githubId?: string
  createdAt: Date
  updatedAt: Date
}

declare module "next-auth" {
  interface Session {
    user: {
      id: string
      name?: string | null
      email?: string | null
      image?: string | null
    }
    accessToken?: string
  }
}

export interface Project {
  id: string
  name: string
  gitRepoUrl: string
  teamId: string
  autoDeployEnabled: boolean
  webhookId?: string
  webhookConfigured: boolean
  team?: {
    id: string
    name: string
  }
  createdAt: Date
  updatedAt: Date
  // Legacy fields for backward compatibility (these are now in Environment model)
  branch?: string
  userId?: string
  status?: ProjectStatus
  ecsClusterArn?: string
  ecsServiceArn?: string
  albArn?: string
  domain?: string
  secretsArn?: string
  existingVpcId?: string
  existingSubnetIds?: string
  existingClusterArn?: string
  cpu?: number
  memory?: number
  diskSize?: number
  subdirectory?: string
  port?: number
  healthCheckPath?: string
}

export enum ProjectStatus {
  CREATED = 'CREATED',
  CLONING = 'CLONING',
  BUILDING = 'BUILDING',
  DEPLOYING = 'DEPLOYING',
  DEPLOYED = 'DEPLOYED',
  FAILED = 'FAILED'
}

export interface Deployment {
  id: string
  projectId: string
  environmentId?: string
  status: DeploymentStatus
  imageTag: string
  commitSha: string
  logs?: string
  details?: string
  createdAt: Date
  updatedAt: Date
  environment?: {
    id: string
    name: string
  }
}

export enum DeploymentStatus {
  PENDING = 'PENDING',
  BUILDING = 'BUILDING',
  PUSHING = 'PUSHING',
  PROVISIONING = 'PROVISIONING',
  DEPLOYING = 'DEPLOYING',
  SUCCESS = 'SUCCESS',
  FAILED = 'FAILED'
}

export interface EnvironmentVariable {
  id: string
  environmentId: string
  projectId: string
  key: string
  value?: string
  isSecret: boolean
  secretKey?: string
  createdAt: Date
  updatedAt: Date
}

export enum TeamMemberRole {
  OWNER = 'OWNER',
  ADMIN = 'ADMIN',
  MEMBER = 'MEMBER'
}


export interface TeamMember {
  id: string
  teamId: string
  userId: string
  role: TeamMemberRole
  joinedAt: Date
  user?: {
    id: string
    name?: string
    email?: string
    image?: string
  }
}

export interface Team {
  id: string
  name: string
  description?: string
  ownerId: string
  createdAt: Date
  updatedAt: Date
  members?: TeamMember[]
  memberCount?: number
  userRole?: TeamMemberRole
}

export interface Environment {
  id: string
  name: string
  projectId?: string
  projectName?: string
  branch: string
  status: ProjectStatus
  domain?: string
  certificateArn?: string
  enableHttps?: boolean
  autoProvisionCertificate?: boolean
  useRoute53Validation?: boolean
  cpu: number
  memory: number
  diskSize?: number
  port: number
  healthCheckPath: string
  subdirectory?: string
  existingVpcId?: string
  existingSubnetIds?: string
  existingClusterArn?: string
  secretsArn?: string
  ecsClusterArn?: string
  ecsServiceArn?: string
  albArn?: string
  albDns?: string
  awsConfig: {
    id: string
    name: string
    region: string
    type: string
  }
  latestDeployment?: {
    id: string
    status: DeploymentStatus
    createdAt: Date
  }
  deployments?: Array<{
    id: string
    status: DeploymentStatus
    imageTag: string
    commitSha: string
    createdAt: Date
  }>
  createdAt: Date
  updatedAt: Date
}

