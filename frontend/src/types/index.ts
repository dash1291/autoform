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
  branch: string
  userId: string
  teamId?: string
  status: ProjectStatus
  ecsClusterArn?: string
  ecsServiceArn?: string
  albArn?: string
  domain?: string
  secretsArn?: string
  existingVpcId?: string
  existingSubnetIds?: string
  existingClusterArn?: string
  cpu: number
  memory: number
  diskSize: number
  subdirectory?: string
  port: number
  healthCheckPath: string
  autoDeployEnabled: boolean
  webhookSecret?: string
  webhookConfigured: boolean
  team?: {
    id: string
    name: string
  }
  createdAt: Date
  updatedAt: Date
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
  status: DeploymentStatus
  imageTag: string
  commitSha: string
  logs?: string
  details?: string
  createdAt: Date
  updatedAt: Date
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

