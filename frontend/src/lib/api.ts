import { useJwtStore } from './auth-client'
import { Project, Team, TeamMember, EnvironmentVariable, Deployment } from '../types'

class ApiClient {
  private baseUrl: string

  constructor() {
    // Use the build-time environment variable for API URL
    this.baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  }

  private getAuthHeaders(): HeadersInit {
    const { jwtToken } = useJwtStore.getState()
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    }

    if (jwtToken) {
      headers.Authorization = `Bearer ${jwtToken}`
    }

    return headers
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    isRetry: boolean = false
  ): Promise<T> {
    const url = `${this.baseUrl}/api${endpoint}`
    const headers = this.getAuthHeaders()

    const config: RequestInit = {
      ...options,
      headers: {
        ...headers,
        ...options.headers,
      },
    }

    const response = await fetch(url, config)

    // Handle 401 errors by trying to refresh the token
    if (response.status === 401 && !isRetry) {
      try {
        // Try to refresh the JWT token
        await this.refreshToken()
        
        // Retry the request with the new token
        return this.request(endpoint, options, true)
      } catch (refreshError) {
        // If refresh fails, clear the token and throw the original error
        useJwtStore.getState().clearJwtToken()
        const error = await response.json().catch(() => ({ message: 'Authentication failed' }))
        throw new Error(error.message || `HTTP ${response.status}`)
      }
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Network error' }))
      throw new Error(error.message || `HTTP ${response.status}`)
    }

    return response.json()
  }

  private async refreshToken(): Promise<void> {
    // Import dynamically to avoid circular dependencies
    const { getSession } = await import('next-auth/react')
    const session = await getSession()
    
    if (!session?.user) {
      throw new Error('No session available for token refresh')
    }

    const response = await fetch(`${this.baseUrl}/api/auth/exchange-session`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        sessionUser: session.user,
        accessToken: session.accessToken,
      }),
    })

    if (response.ok) {
      const data = await response.json()
      useJwtStore.getState().setJwtToken(data.access_token)
    } else {
      throw new Error('Token refresh failed')
    }
  }

  // Auth endpoints - Note: login/register are handled via GitHub OAuth

  // Project endpoints
  async getProjects(): Promise<Project[]> {
    return this.request<Project[]>('/projects/')
  }

  async getProject(id: string): Promise<Project> {
    return this.request<Project>(`/projects/${id}`)
  }

  async createProject(projectData: any): Promise<Project> {
    return this.request<Project>('/projects/', {
      method: 'POST',
      body: JSON.stringify(projectData),
    })
  }

  async updateProject(id: string, projectData: any): Promise<Project & { healthCheckUpdateStatus?: string }> {
    return this.request<Project & { healthCheckUpdateStatus?: string }>(`/projects/${id}`, {
      method: 'PUT',
      body: JSON.stringify(projectData),
    })
  }

  async deleteProject(id: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/projects/${id}`, {
      method: 'DELETE',
    })
  }

  // Deployment endpoints
  async getDeployments(projectId: string): Promise<Deployment[]> {
    return this.request<Deployment[]>(`/deployments/projects/${projectId}/deployments`)
  }

  async deployProject(projectId: string): Promise<{ message: string; deploymentId?: string }> {
    return this.request<{ message: string; deploymentId?: string }>(`/deployments/projects/${projectId}/deploy`, {
      method: 'POST',
    })
  }

  async abortDeployment(deploymentId: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/deployments/${deploymentId}/abort`, {
      method: 'POST',
    })
  }

  async getDeploymentLogs(deploymentId: string): Promise<{ logs: string }> {
    return this.request<{ logs: string }>(`/deployments/${deploymentId}/logs`)
  }

  // Environment variables endpoints
  async getEnvironmentVariables(projectId: string): Promise<Array<Omit<EnvironmentVariable, 'createdAt' | 'updatedAt'> & { createdAt: string; updatedAt: string }>> {
    return this.request<Array<Omit<EnvironmentVariable, 'createdAt' | 'updatedAt'> & { createdAt: string; updatedAt: string }>>(`/projects/${projectId}/environment-variables/`)
  }

  async createEnvironmentVariable(projectId: string, envVar: any): Promise<EnvironmentVariable> {
    return this.request<EnvironmentVariable>(`/projects/${projectId}/environment-variables/`, {
      method: 'POST',
      body: JSON.stringify(envVar),
    })
  }

  async updateEnvironmentVariable(projectId: string, envVarId: string, envVar: any): Promise<EnvironmentVariable> {
    return this.request<EnvironmentVariable>(`/projects/${projectId}/environment-variables/${envVarId}`, {
      method: 'PUT',
      body: JSON.stringify(envVar),
    })
  }

  async deleteEnvironmentVariable(projectId: string, envVarId: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/projects/${projectId}/environment-variables/${envVarId}`, {
      method: 'DELETE',
    })
  }

  // GitHub endpoints
  async validateRepository(repoUrl: string): Promise<{
    valid: boolean
    repository?: {
      name: string
      fullName: string
      private: boolean
      defaultBranch: string
      description?: string
      branches: string[]
    }
    error?: string
    needsReauth?: boolean
  }> {
    return this.request<{
      valid: boolean
      repository?: {
        name: string
        fullName: string
        private: boolean
        defaultBranch: string
        description?: string
        branches: string[]
      }
      error?: string
      needsReauth?: boolean
    }>('/github/validate-repo', {
      method: 'POST',
      body: JSON.stringify({ gitRepoUrl: repoUrl }),
    })
  }

  // Note: Branch information is included in validateRepository response

  // Service status endpoints  
  async getServiceStatus(projectId: string): Promise<any> {
    return this.request<any>(`/projects/${projectId}/service-status`)
  }

  // Shell execution endpoints
  async checkExecAvailability(projectId: string): Promise<{ available: boolean; status: string; reason?: string; clusterArn?: string; taskArn?: string; containerName?: string; region?: string }> {
    return this.request<{ available: boolean; status: string; reason?: string; clusterArn?: string; taskArn?: string; containerName?: string; region?: string }>(`/projects/${projectId}/exec`)
  }

  async executeCommand(projectId: string, command: string): Promise<{ success: boolean; sessionId?: string; streamUrl?: string; tokenValue?: string; message?: string }> {
    return this.request<{ success: boolean; sessionId?: string; streamUrl?: string; tokenValue?: string; message?: string }>(`/projects/${projectId}/exec/command`, {
      method: 'POST',
      body: JSON.stringify({ command }),
    })
  }

  // Logs endpoints
  async getProjectLogs(projectId: string, limit: number = 100, hoursBack?: number): Promise<{ logs: any[]; logGroupName: string; totalStreams: number; message?: string }> {
    let url = `/projects/${projectId}/logs?limit=${limit}`
    if (hoursBack !== undefined) {
      url += `&hours_back=${hoursBack}`
    }
    return this.request<{ logs: any[]; logGroupName: string; totalStreams: number; message?: string }>(url)
  }

  async getCodeBuildLogs(projectId: string, limit: number = 100): Promise<{ logs: any[]; logGroupName: string; totalStreams: number; message?: string }> {
    return this.request<{ logs: any[]; logGroupName: string; totalStreams: number; message?: string }>(`/projects/${projectId}/codebuild-logs?limit=${limit}`)
  }

  // AWS resources endpoints
  async getAwsResources(credentialType: string = 'auto', teamId?: string): Promise<{ vpcs: any[]; subnetsByVpc: any; clusters: any[]; message?: string }> {
    let url = `/aws/resources?credential_type=${credentialType}`
    if (teamId) {
      url += `&team_id=${teamId}`
    }
    return this.request<{ vpcs: any[]; subnetsByVpc: any; clusters: any[]; message?: string }>(url)
  }

  async getProjectDeployedResources(projectId: string): Promise<any> {
    return this.request<any>(`/projects/${projectId}/deployed-resources`)
  }

  // Webhook endpoints
  async configureWebhook(projectId: string, githubAccessToken?: string): Promise<{
    webhookUrl: string
    webhookSecret: string
    instructions?: Record<string, string>
    automatic?: boolean
    status?: string
    webhookId?: string
  }> {
    const headers: HeadersInit = {}
    if (githubAccessToken) {
      headers['X-GitHub-Token'] = githubAccessToken
    }
    
    return this.request<{
      webhookUrl: string
      webhookSecret: string
      instructions?: Record<string, string>
      automatic?: boolean
      status?: string
      webhookId?: string
    }>(`/projects/${projectId}/webhook/configure`, {
      method: 'POST',
      headers
    })
  }

  async deleteWebhookConfig(projectId: string, githubAccessToken?: string) {
    const headers: HeadersInit = {}
    if (githubAccessToken) {
      headers['X-GitHub-Token'] = githubAccessToken
    }
    
    return this.request(`/projects/${projectId}/webhook`, {
      method: 'DELETE',
      headers
    })
  }

  // Team endpoints
  async getTeams(): Promise<Team[]> {
    return this.request<Team[]>('/teams/')
  }

  async getTeam(teamId: string): Promise<Team> {
    return this.request<Team>(`/teams/${teamId}`)
  }

  async createTeam(teamData: { name: string; description?: string }) {
    return this.request('/teams/', {
      method: 'POST',
      body: JSON.stringify(teamData),
    })
  }

  async updateTeam(teamId: string, teamData: { name?: string; description?: string }) {
    return this.request(`/teams/${teamId}`, {
      method: 'PUT',
      body: JSON.stringify(teamData),
    })
  }

  async deleteTeam(teamId: string) {
    return this.request(`/teams/${teamId}`, {
      method: 'DELETE',
    })
  }

  async addTeamMember(teamId: string, memberData: { githubUsername: string; role: string }) {
    return this.request(`/teams/${teamId}/members`, {
      method: 'POST',
      body: JSON.stringify(memberData),
    })
  }

  async removeTeamMember(teamId: string, memberId: string) {
    return this.request(`/teams/${teamId}/members/${memberId}`, {
      method: 'DELETE',
    })
  }

  async updateTeamMemberRole(teamId: string, memberId: string, role: string) {
    return this.request(`/teams/${teamId}/members/${memberId}/role`, {
      method: 'PUT',
      body: JSON.stringify({ role }),
    })
  }

  // Team AWS Configuration endpoints
  async getTeamAwsConfig(teamId: string): Promise<{
    awsAccessKeyId: string
    awsSecretAccessKey: string
    awsRegion: string
    isActive: boolean
    createdAt: string
    updatedAt: string
  }> {
    return this.request<{
      awsAccessKeyId: string
      awsSecretAccessKey: string
      awsRegion: string
      isActive: boolean
      createdAt: string
      updatedAt: string
    }>(`/teams/${teamId}/aws-config`)
  }

  async createTeamAwsConfig(teamId: string, awsConfig: { 
    awsAccessKeyId: string
    awsSecretAccessKey: string
    awsRegion: string 
  }) {
    return this.request(`/teams/${teamId}/aws-config`, {
      method: 'POST',
      body: JSON.stringify(awsConfig),
    })
  }

  async deleteTeamAwsConfig(teamId: string) {
    return this.request(`/teams/${teamId}/aws-config`, {
      method: 'DELETE',
    })
  }

  async testTeamAwsConfig(teamId: string) {
    return this.request(`/teams/${teamId}/aws-config/test`, {
      method: 'POST',
    })
  }

  // User AWS Configuration endpoints
  async getUserAwsConfig(): Promise<{
    configured: boolean
    region: string | null
    accessKeyId?: string
    createdAt?: string
    updatedAt?: string
  }> {
    return this.request<{
      configured: boolean
      region: string | null
      accessKeyId?: string
      createdAt?: string
      updatedAt?: string
    }>('/aws/user-credentials')
  }

  async saveUserAwsConfig(awsConfig: { 
    accessKeyId: string
    secretAccessKey: string
    region: string 
  }) {
    return this.request('/aws/user-credentials', {
      method: 'POST',
      body: JSON.stringify(awsConfig),
    })
  }

  async deleteUserAwsConfig() {
    return this.request('/aws/user-credentials', {
      method: 'DELETE',
    })
  }

  // Test AWS credentials (works for both team and personal)
  async testAwsCredentials(credentialType: string = 'auto') {
    return this.request(`/aws/credentials-check?credential_type=${credentialType}`)
  }
}

export const apiClient = new ApiClient()
export default apiClient