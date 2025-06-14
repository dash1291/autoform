'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { Project, Deployment } from '@/types'
import LogsViewer from '@/components/LogsViewer'
import EnvironmentVariables from '@/components/EnvironmentVariables'
import SimpleShell from '@/components/SimpleShell'
import NetworkConfiguration from '@/components/NetworkConfiguration'
import ResourceConfiguration from '@/components/ResourceConfiguration'
import RepositoryConfiguration from '@/components/RepositoryConfiguration'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Clock, GitCommit } from 'lucide-react'
import { useAuth } from '@/lib/auth-client'
import { apiClient } from '@/lib/api'

export default function ProjectDetail() {
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const params = useParams()
  const router = useRouter()
  const [project, setProject] = useState<Project | null>(null)
  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [liveLogs, setLiveLogs] = useState<string>('')
  const [activeDeploymentId, setActiveDeploymentId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'overview' | 'deployments' | 'logs' | 'settings' | 'shell'>('overview')
  const [activeSettingsTab, setActiveSettingsTab] = useState<'environment' | 'repository' | 'resources'>('repository')

  useEffect(() => {
    if (isAuthenticated && !authLoading && params.id) {
      fetchProject()
      fetchDeployments()
    } else if (!authLoading && !isAuthenticated) {
      setLoading(false)
    }
  }, [isAuthenticated, authLoading, params.id])

  // Poll for live logs when there's an active deployment
  useEffect(() => {
    let interval: NodeJS.Timeout | null = null

    if (activeDeploymentId) {
      // Fetch logs immediately
      fetchLiveLogs(activeDeploymentId)
      
      // Set up polling every 2 seconds
      interval = setInterval(() => {
        fetchLiveLogs(activeDeploymentId)
        fetchProject() // Also refresh project status
        fetchDeployments() // Refresh deployment status
      }, 2000)
    }

    return () => {
      if (interval) {
        clearInterval(interval)
      }
    }
  }, [activeDeploymentId])

  const fetchProject = async () => {
    try {
      const data = await apiClient.getProject(params.id as string)
      setProject(data)
    } catch (err: any) {
      if (err.message.includes('404')) {
        setError('Project not found')
      } else {
        setError('Failed to fetch project')
      }
    } finally {
      setLoading(false)
    }
  }

  const fetchDeployments = async () => {
    try {
      const data = await apiClient.getDeployments(params.id as string)
      setDeployments(data)
      
      // Find active deployment for live logs
      const activeDeployment = data.find((d: Deployment) => 
        ['PENDING', 'BUILDING', 'PUSHING', 'PROVISIONING', 'DEPLOYING'].includes(d.status)
      )
      
      if (activeDeployment) {
        setActiveDeploymentId(activeDeployment.id)
      } else {
        setActiveDeploymentId(null)
        setLiveLogs('')
      }
    } catch (err) {
      console.error('Failed to fetch deployments:', err)
    }
  }

  const fetchLiveLogs = async (deploymentId: string) => {
    try {
      const data = await apiClient.getDeploymentLogs(deploymentId)
      setLiveLogs(data.logs || '')
    } catch (err) {
      console.error('Failed to fetch live logs:', err)
    }
  }

  const handleDeploy = async () => {
    if (!project) return
    
    try {
      await apiClient.deployProject(project.id)
      // Refresh project and deployments
      fetchProject()
      fetchDeployments()
    } catch (err) {
      setError('Failed to start deployment')
    }
  }

  const handleAbortDeployment = async () => {
    if (!project || !confirm('Are you sure you want to abort the current deployment?')) return
    
    try {
      await apiClient.abortDeployment(project.id)
      // Refresh project and deployments
      fetchProject()
      fetchDeployments()
    } catch (err) {
      setError('Failed to abort deployment')
    }
  }

  const handleDelete = async () => {
    if (!project || !confirm('Are you sure you want to delete this project?')) return
    
    try {
      await apiClient.deleteProject(project.id)
      router.push('/dashboard')
    } catch (err) {
      setError('Failed to delete project')
    }
  }

  if (!authLoading && !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Please sign in</h1>
          <p className="text-gray-600">You need to be signed in to view this project.</p>
        </div>
      </div>
    )
  }

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  if (error || !project) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Project Not Found</h1>
          <p className="text-gray-600 mb-4">{error || 'The project you are looking for does not exist.'}</p>
          <Link
            href="/dashboard"
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
          >
            Back to Dashboard
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div>
              <Link
                href="/dashboard"
                className="text-blue-600 hover:text-blue-700 text-sm mb-2 inline-block"
              >
                ← Back to Dashboard
              </Link>
              <h1 className="text-3xl font-bold text-gray-900">{project.name}</h1>
              <p className="text-gray-600">{project.gitRepoUrl}</p>
            </div>
            {project.status === 'DEPLOYING' || project.status === 'BUILDING' || project.status === 'CLONING' ? (
              <div className="flex space-x-3">
                <Button disabled variant="secondary">
                  {project.status === 'DEPLOYING' ? 'Deploying...' : 
                   project.status === 'BUILDING' ? 'Building...' : 
                   'Cloning...'}
                </Button>
                <Button
                  onClick={handleAbortDeployment}
                  variant="destructive"
                >
                  Abort Deployment
                </Button>
              </div>
            ) : null}
          </div>
        </div>

        {/* Tabs */}
        <div className="mb-6">
          <div className="border-b border-gray-200">
            <nav className="-mb-px flex space-x-8">
              <Button
                variant="ghost"
                onClick={() => setActiveTab('overview')}
                className={`py-2 px-1 border-b-2 font-medium text-sm rounded-none ${
                  activeTab === 'overview'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
                }`}
              >
                Overview
              </Button>
              <Button
                variant="ghost"
                onClick={() => setActiveTab('deployments')}
                className={`py-2 px-1 border-b-2 font-medium text-sm rounded-none ${
                  activeTab === 'deployments'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
                }`}
              >
                Deployments ({deployments.length})
              </Button>
              <Button
                variant="ghost"
                onClick={() => setActiveTab('logs')}
                className={`py-2 px-1 border-b-2 font-medium text-sm rounded-none ${
                  activeTab === 'logs'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
                }`}
              >
                Application Logs
              </Button>
              <Button
                variant="ghost"
                onClick={() => setActiveTab('shell')}
                className={`py-2 px-1 border-b-2 font-medium text-sm rounded-none ${
                  activeTab === 'shell'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
                }`}
              >
                Shell Access
              </Button>
              <Button
                variant="ghost"
                onClick={() => setActiveTab('settings')}
                className={`py-2 px-1 border-b-2 font-medium text-sm rounded-none ${
                  activeTab === 'settings'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
                }`}
              >
                Settings
              </Button>
            </nav>
          </div>
        </div>

        <div className="space-y-6">
          {activeTab === 'overview' && (
            <>
              {/* Status Card */}
              <div className="bg-white shadow rounded-lg p-6">
                <h2 className="text-xl font-semibold text-gray-900 mb-4">Project Status</h2>
                <div className="space-y-4">
                  <div>
                    <span className="text-sm font-medium text-gray-500">Current Status</span>
                    <div className="mt-1">
                      <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                        project.status === 'DEPLOYED' ? 'bg-green-100 text-green-800' :
                        project.status === 'FAILED' ? 'bg-red-100 text-red-800' :
                        'bg-yellow-100 text-yellow-800'
                      }`}>
                        {project.status}
                      </span>
                    </div>
                  </div>
                  
                  {project.domain && (
                    <div>
                      <span className="text-sm font-medium text-gray-500">Application URL</span>
                      <div className="mt-1">
                        <a
                          href={`http://${project.domain}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:text-blue-700"
                        >
                          {project.domain}
                        </a>
                      </div>
                    </div>
                  )}
                  
                  <div>
                    <span className="text-sm font-medium text-gray-500">Created</span>
                    <div className="mt-1 text-sm text-gray-900">
                      {new Date(project.createdAt).toLocaleString()}
                    </div>
                  </div>
                  
                  <div>
                    <span className="text-sm font-medium text-gray-500">Last Updated</span>
                    <div className="mt-1 text-sm text-gray-900">
                      {new Date(project.updatedAt).toLocaleString()}
                    </div>
                  </div>
                </div>
              </div>

              {/* Live Deployment Logs */}
              {activeDeploymentId && liveLogs && (
                <div className="bg-white shadow rounded-lg p-6">
                  <h2 className="text-xl font-semibold text-gray-900 mb-4">
                    🔴 Live Deployment Logs
                  </h2>
                  <div className="bg-gray-900 text-green-400 p-4 rounded-lg overflow-auto max-h-96 font-mono text-sm">
                    <pre className="whitespace-pre-wrap">{liveLogs}</pre>
                  </div>
                  <p className="text-sm text-gray-500 mt-2">
                    Logs update automatically every 2 seconds
                  </p>
                </div>
              )}
            </>
          )}

          {activeTab === 'deployments' && (
            <div className="bg-white shadow rounded-lg p-6">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-xl font-semibold text-gray-900">Deployment History</h2>
                {project.status !== 'DEPLOYING' && project.status !== 'BUILDING' && project.status !== 'CLONING' && (
                  <Button onClick={handleDeploy}>
                    Deploy
                  </Button>
                )}
              </div>
              {deployments.length === 0 ? (
                <p className="text-gray-500">No deployments yet.</p>
              ) : (
                <div className="space-y-4">
                  {deployments.map((deployment) => (
                    <div key={deployment.id} className="border border-gray-200 rounded-lg p-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-3">
                          <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                            deployment.status === 'SUCCESS' ? 'bg-green-100 text-green-800' :
                            deployment.status === 'FAILED' ? 'bg-red-100 text-red-800' :
                            'bg-yellow-100 text-yellow-800'
                          }`}>
                            {deployment.status}
                          </span>
                          <div className="flex items-center space-x-1">
                            <GitCommit className="h-3 w-3 text-gray-500" />
                            <code className="text-sm bg-gray-100 px-2 py-1 rounded">
                              {deployment.commitSha.substring(0, 8)}
                            </code>
                          </div>
                          <div className="flex items-center space-x-1">
                            <Clock className="h-3 w-3 text-gray-500" />
                            <span className="text-sm text-gray-600">
                              {new Date(deployment.createdAt).toLocaleDateString('en-US', {
                                month: 'short',
                                day: 'numeric',
                                year: 'numeric'
                              })} {new Date(deployment.createdAt).toLocaleTimeString('en-US', {
                                hour: 'numeric',
                                minute: '2-digit',
                                hour12: true
                              })}
                            </span>
                          </div>
                        </div>
                      </div>
                      {deployment.logs && (
                        <div className="mt-3">
                          <details className="text-sm">
                            <summary className="cursor-pointer text-gray-600">View Deployment Logs</summary>
                            <pre className="mt-2 bg-gray-50 p-3 rounded text-xs overflow-auto max-h-48">
                              {deployment.logs}
                            </pre>
                          </details>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {activeTab === 'logs' && (
            <div className="bg-white shadow rounded-lg p-6">
              <h2 className="text-xl font-semibold text-gray-900 mb-4">Application Logs</h2>
              <LogsViewer projectId={params.id as string} />
            </div>
          )}

          {activeTab === 'settings' && (
            <div className="bg-white shadow rounded-lg overflow-hidden">
              <div className="flex">
                {/* Vertical sidebar navigation */}
                <div className="w-64 bg-gray-50 border-r border-gray-200">
                  <nav className="p-4 space-y-2">
                    <Button
                      variant={activeSettingsTab === 'repository' ? 'secondary' : 'ghost'}
                      onClick={() => setActiveSettingsTab('repository')}
                      className="w-full justify-start text-sm font-medium"
                    >
                      Git Repository
                    </Button>
                    <Button
                      variant={activeSettingsTab === 'environment' ? 'secondary' : 'ghost'}
                      onClick={() => setActiveSettingsTab('environment')}
                      className="w-full justify-start text-sm font-medium"
                    >
                      Environment Variables
                    </Button>
                    <Button
                      variant={activeSettingsTab === 'resources' ? 'secondary' : 'ghost'}
                      onClick={() => setActiveSettingsTab('resources')}
                      className="w-full justify-start text-sm font-medium"
                    >
                      AWS Resources
                    </Button>
                  </nav>
                </div>

                {/* Content area */}
                <div className="flex-1 p-6">
                  {activeSettingsTab === 'environment' && (
                    <EnvironmentVariables projectId={params.id as string} />
                  )}

                  {activeSettingsTab === 'repository' && (
                    <RepositoryConfiguration 
                      projectId={params.id as string} 
                      project={project}
                      onUpdate={fetchProject}
                    />
                  )}

                  {activeSettingsTab === 'resources' && (
                    <div className="space-y-6">
                      <ResourceConfiguration 
                        projectId={params.id as string} 
                        project={project}
                        onUpdate={fetchProject}
                      />
 
                      <NetworkConfiguration 
                        projectId={params.id as string} 
                        project={project}
                        onUpdate={fetchProject}
                      />

                      <div className="bg-white border border-gray-200 rounded-lg p-6">
                        <h2 className="text-xl font-semibold text-gray-900 mb-4">Other Resources</h2>
                        <div className="space-y-3">
                          {project.albArn && (
                            <div className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded-lg">
                              <div>
                                <span className="text-sm font-medium text-gray-900">Load Balancer</span>
                                <p className="text-xs text-gray-500 truncate max-w-full">{project.albArn}</p>
                              </div>
                            </div>
                          )}
                          
                          <div className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded-lg">
                            <div>
                              <span className="text-sm font-medium text-gray-900">Logs</span>
                              <p className="text-xs text-gray-500">/ecs/{project.name}</p>
                            </div>
                          </div>
                          
                          <div className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded-lg">
                            <div>
                              <span className="text-sm font-medium text-gray-900">Container Registry</span>
                              <p className="text-xs text-gray-500">{project.name.toLowerCase().replace(/[^a-z0-9-_]/g, '-')}</p>
                            </div>
                          </div>
                        </div>

                        {!project.albArn && (
                          <div className="text-center py-4">
                            <p className="text-sm text-gray-500">Deploy project to see resources</p>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'shell' && (
            <div className="bg-white shadow rounded-lg p-6">
              <SimpleShell projectId={params.id as string} isActive={activeTab === 'shell'} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}