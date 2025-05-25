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
  status: ProjectStatus
  ecsClusterArn?: string
  ecsServiceArn?: string
  albArn?: string
  domain?: string
  secretsArn?: string
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