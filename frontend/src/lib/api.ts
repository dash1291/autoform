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
    options: RequestInit = {}
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

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Network error' }))
      throw new Error(error.message || `HTTP ${response.status}`)
    }

    return response.json()
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