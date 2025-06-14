import { useJwtStore } from './auth-client'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

class ApiClient {
  private baseUrl: string

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl
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
      headers,
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

  // Auth endpoints
  async login(credentials: { username: string; password: string }) {
    return this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    })
  }

  async register(userData: { username: string; email: string; password: string }) {
    return this.request('/auth/register', {
      method: 'POST',
      body: JSON.stringify(userData),
    })
  }

  // Project endpoints
  async getProjects() {
    return this.request('/projects')
  }

  async getProject(id: string) {
    return this.request(`/projects/${id}`)
  }

  async createProject(projectData: any) {
    return this.request('/projects', {
      method: 'POST',
      body: JSON.stringify(projectData),
    })
  }

  async updateProject(id: string, projectData: any) {
    return this.request(`/projects/${id}`, {
      method: 'PUT',
      body: JSON.stringify(projectData),
    })
  }

  async deleteProject(id: string) {
    return this.request(`/projects/${id}`, {
      method: 'DELETE',
    })
  }

  // Deployment endpoints
  async getDeployments(projectId: string) {
    return this.request(`/deployments/projects/${projectId}/deployments`)
  }

  async deployProject(projectId: string) {
    return this.request(`/deployments/projects/${projectId}/deploy`, {
      method: 'POST',
    })
  }

  async abortDeployment(projectId: string) {
    return this.request(`/deployments/projects/${projectId}/abort`, {
      method: 'POST',
    })
  }

  async getDeploymentLogs(deploymentId: string) {
    return this.request(`/deployments/${deploymentId}/logs`)
  }

  // Environment variables endpoints
  async getEnvironmentVariables(projectId: string) {
    return this.request(`/projects/${projectId}/environment-variables`)
  }

  async createEnvironmentVariable(projectId: string, envVar: any) {
    return this.request(`/projects/${projectId}/environment-variables`, {
      method: 'POST',
      body: JSON.stringify(envVar),
    })
  }

  async updateEnvironmentVariable(projectId: string, envVarId: string, envVar: any) {
    return this.request(`/projects/${projectId}/environment-variables/${envVarId}`, {
      method: 'PUT',
      body: JSON.stringify(envVar),
    })
  }

  async deleteEnvironmentVariable(projectId: string, envVarId: string) {
    return this.request(`/projects/${projectId}/environment-variables/${envVarId}`, {
      method: 'DELETE',
    })
  }

  // GitHub endpoints
  async validateRepository(repoUrl: string) {
    return this.request('/github/validate-repo', {
      method: 'POST',
      body: JSON.stringify({ gitRepoUrl: repoUrl }),
    })
  }

  async getBranches(repoUrl: string) {
    return this.request('/github/branches', {
      method: 'POST',
      body: JSON.stringify({ repoUrl }),
    })
  }

  // Service status endpoints  
  async getServiceStatus(projectId: string) {
    return this.request(`/projects/${projectId}/service-status`)
  }

  // Shell execution endpoints
  async checkExecAvailability(projectId: string) {
    return this.request(`/projects/${projectId}/exec`)
  }

  async executeCommand(projectId: string, command: string) {
    return this.request(`/projects/${projectId}/exec/command`, {
      method: 'POST',
      body: JSON.stringify({ command }),
    })
  }

  // Logs endpoints
  async getProjectLogs(projectId: string, limit: number = 100) {
    return this.request(`/projects/${projectId}/logs?limit=${limit}`)
  }

  async getCodeBuildLogs(projectId: string, limit: number = 100) {
    return this.request(`/projects/${projectId}/codebuild-logs?limit=${limit}`)
  }

  // AWS resources endpoints
  async getAwsResources() {
    return this.request('/aws/resources')
  }

  async getProjectDeployedResources(projectId: string) {
    return this.request(`/projects/${projectId}/deployed-resources`)
  }
}

export const apiClient = new ApiClient()
export default apiClient