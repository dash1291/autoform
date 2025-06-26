'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Project, Deployment, Environment } from '@/types'
import LogsViewer from '@/components/LogsViewer'
import EnvironmentVariables from '@/components/EnvironmentVariables'
import EnvironmentManagement from '@/components/EnvironmentManagement'
import DeploymentModal from '@/components/DeploymentModal'
import SimpleShell from '@/components/SimpleShell'
import NetworkConfiguration from '@/components/NetworkConfiguration'
import ResourceConfiguration from '@/components/ResourceConfiguration'
import RepositoryConfiguration from '@/components/RepositoryConfiguration'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Clock, GitCommit, Server } from 'lucide-react'
import { useAuth } from '@/lib/auth-client'
import { apiClient } from '@/lib/api'

export default function ProjectDetail() {
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const params = useParams()
  const router = useRouter()
  const searchParams = useSearchParams()
  const [project, setProject] = useState<Project | null>(null)
  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [liveLogs, setLiveLogs] = useState<string>('')
  const [activeDeploymentId, setActiveDeploymentId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'overview' | 'deployments' | 'logs' | 'settings' | 'shell'>('overview')
  const [selectedEnvironment, setSelectedEnvironment] = useState<Environment | null>(null)
  const [activeSettingsTab, setActiveSettingsTab] = useState<'environment' | 'environments' | 'repository' | 'resources'>('repository')
  const [environments, setEnvironments] = useState<Environment[]>([])
  const [selectedEnvironmentForVars, setSelectedEnvironmentForVars] = useState<string | null>(null)
  const [serviceStatus, setServiceStatus] = useState<any>(null)
  const [awsRegion, setAwsRegion] = useState<string | null>(null)
  const [deploymentModalOpen, setDeploymentModalOpen] = useState(false)

  useEffect(() => {
    if (isAuthenticated && !authLoading && params.id) {
      fetchProject()
      fetchDeployments()
      fetchEnvironments()
    } else if (!authLoading && !isAuthenticated) {
      setLoading(false)
    }
  }, [isAuthenticated, authLoading, params.id])

  // Handle tab query parameter
  useEffect(() => {
    const tab = searchParams.get('tab')
    if (tab && ['overview', 'environments', 'deployments', 'logs', 'settings', 'shell'].includes(tab)) {
      setActiveTab(tab as any)
    }
  }, [searchParams])

  // Fetch service status when project loads and periodically
  useEffect(() => {
    if (project?.ecsServiceArn) {
      fetchServiceStatus()
      
      // Refresh service status every 30 seconds
      const interval = setInterval(fetchServiceStatus, 30000)
      return () => clearInterval(interval)
    }
  }, [project?.ecsServiceArn])

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
      // Fetch AWS region based on project ownership
      await fetchAwsRegion(data)
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

  const fetchAwsRegion = async (projectData: any) => {
    try {
      if (projectData.teamId) {
        // Team project - get team AWS config
        const config = await apiClient.getTeamAwsConfig(projectData.teamId)
        setAwsRegion(config.awsRegion)
      } else {
        // Personal project - get user AWS config
        const config = await apiClient.getUserAwsConfig()
        setAwsRegion(config.region)
      }
    } catch (err) {
      console.error('Failed to fetch AWS region:', err)
      setAwsRegion(null)
    }
  }

  const fetchEnvironments = async () => {
    try {
      const data = await apiClient.getProjectEnvironments(params.id as string)
      setEnvironments(data)
      // Set default selected environment for variables if none selected
      if (!selectedEnvironmentForVars && data.length > 0) {
        setSelectedEnvironmentForVars(data[0].id)
      }
    } catch (err) {
      console.error('Failed to fetch environments:', err)
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

  const fetchServiceStatus = async () => {
    if (!project?.ecsServiceArn) return
    
    try {
      const status = await apiClient.getServiceStatus(params.id as string)
      setServiceStatus(status)
    } catch (err) {
      console.error('Failed to fetch service status:', err)
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
    setDeploymentModalOpen(true)
  }

  const handleDeploymentStarted = (deploymentId: string, environmentId: string) => {
    // Refresh project and deployments when deployment starts
    fetchProject()
    fetchDeployments()
  }

  const handleAbortDeployment = async (deploymentId: string) => {
    if (!confirm('Are you sure you want to abort this deployment?')) return
    
    try {
      await apiClient.abortDeployment(deploymentId)
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
            {/* Status is now at environment level */}
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
                    <div className="mt-1 flex items-center space-x-3">
                      <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                        serviceStatus?.status === 'HEALTHY' ? 'bg-green-100 text-green-800' :
                        serviceStatus?.status === 'CRASH_LOOP' ? 'bg-red-100 text-red-800' :
                        serviceStatus?.status === 'IN_PROGRESS' ? 'bg-blue-100 text-blue-800' :
                        serviceStatus?.status === 'DEGRADED' ? 'bg-orange-100 text-orange-800' :
                        serviceStatus?.status === 'NO_RUNNING_TASKS' ? 'bg-gray-100 text-gray-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {serviceStatus?.status || 'Not Deployed'}
                      </span>
                      {serviceStatus && (
                        <span className="text-sm text-gray-600">
                          {serviceStatus.message}
                        </span>
                      )}
                    </div>
                    {serviceStatus?.service && (
                      <div className="mt-2 text-sm text-gray-600">
                        Tasks: {serviceStatus.service.runningCount}/{serviceStatus.service.desiredCount} running
                        {serviceStatus.service.pendingCount > 0 && ` (${serviceStatus.service.pendingCount} pending)`}
                      </div>
                    )}
                    {serviceStatus?.crashLoopDetected && (
                      <div className="mt-2 p-3 bg-red-50 border border-red-200 rounded-md">
                        <p className="text-sm text-red-800">
                          ⚠️ Container crash loop detected. Check the logs for errors.
                        </p>
                      </div>
                    )}
                    {serviceStatus?.failureReasons && serviceStatus.failureReasons.length > 0 && (
                      <div className="mt-2 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
                        <div className="flex items-start">
                          <div className="flex-shrink-0">
                            <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                            </svg>
                          </div>
                          <div className="ml-3">
                            <h4 className="text-sm font-medium text-yellow-800">AWS Messages</h4>
                            <div className="mt-1 text-sm text-yellow-700">
                              <ul className="list-disc list-inside space-y-1">
                                {serviceStatus.failureReasons.map((reason: string, index: number) => (
                                  <li key={index}>{reason}</li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
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
                  <div className="bg-gray-900 text-green-400 p-4 rounded-lg overflow-y-auto max-h-96 font-mono text-sm">
                    <pre className="whitespace-pre-wrap break-words">{liveLogs}</pre>
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
                <Button onClick={handleDeploy}>
                  Deploy
                </Button>
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
                            <Server className="h-3 w-3 text-gray-400" />
                            <span>{deployment.environment?.name || 'Unknown'}</span>
                          </div>
                          <div className="flex items-center space-x-1">
                            <GitCommit className="h-3 w-3 text-gray-500" />
                            {deployment.commitSha ? (
                              (() => {
                                // Extract owner and repo from project.gitRepoUrl
                                let commitUrl = null
                                if (project.gitRepoUrl) {
                                  const match = project.gitRepoUrl.match(/github.com[/:]([^/]+)\/(.+?)(?:\.git)?$/)
                                  if (match) {
                                    const owner = match[1]
                                    const repo = match[2]
                                    commitUrl = `https://github.com/${owner}/${repo}/commit/${deployment.commitSha}`
                                  }
                                }
                                return commitUrl ? (
                                  <a
                                    href={commitUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-sm bg-gray-100 px-2 py-1 rounded hover:underline"
                                  >
                                    {deployment.commitSha.substring(0, 8)}
                                  </a>
                                ) : (
                                  <code className="text-sm bg-gray-100 px-2 py-1 rounded">{deployment.commitSha.substring(0, 8)}</code>
                                )
                              })()
                            ) : (
                              <code className="text-sm bg-gray-100 px-2 py-1 rounded">N/A</code>
                            )}
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
                        {['PENDING', 'BUILDING', 'PUSHING', 'PROVISIONING', 'DEPLOYING'].includes(deployment.status) && (
                          <Button
                            onClick={() => handleAbortDeployment(deployment.id)}
                            variant="destructive"
                            size="sm"
                          >
                            Abort
                          </Button>
                        )}
                      </div>
                      {deployment.logs && deployment.logs.trim() !== '' ? (
                        <div className="mt-3 border-t pt-3">
                          <details className="text-sm">
                            <summary className="cursor-pointer text-gray-600 hover:text-gray-800 font-medium">
                            View Deployment Logs
                            </summary>
                            <pre className="mt-2 bg-gray-900 text-gray-100 p-3 rounded text-xs overflow-y-auto max-h-48 whitespace-pre-wrap break-words font-mono">
                              {deployment.logs}
                            </pre>
                          </details>
                        </div>
                      ) : (
                        <div className="mt-3 text-sm text-gray-500">
                          <em>No logs available for this deployment</em>
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
              <div className="flex justify-between items-center mb-4">
                <div>
                  <h2 className="text-xl font-semibold text-gray-900">Application Logs</h2>
                  <p className="text-sm text-gray-500">
                    View real-time application logs from your deployed environments.
                  </p>
                </div>
                <div className="flex items-center space-x-4">
                  <div className="min-w-[200px]">
                    <Select
                      value={selectedEnvironmentForVars || ''}
                      onValueChange={setSelectedEnvironmentForVars}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select environment" />
                      </SelectTrigger>
                      <SelectContent>
                        {environments.map((env) => (
                          <SelectItem key={env.id} value={env.id}>
                            {env.name} ({env.branch})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <Button
                    onClick={() => {
                      const selectedEnv = environments.find(e => e.id === selectedEnvironmentForVars)
                      if (selectedEnv && project?.name) {
                        const logGroupName = `/ecs/${project.name}-${selectedEnv.name}`
                        const region = selectedEnv.awsConfig?.region || awsRegion
                        const cloudwatchUrl = `https://${region}.console.aws.amazon.com/cloudwatch/home?region=${region}#logsV2:log-groups/log-group/${encodeURIComponent(logGroupName)}`
                        window.open(cloudwatchUrl, '_blank')
                      }
                    }}
                    variant="outline"
                    size="sm"
                    disabled={!selectedEnvironmentForVars}
                  >
                    View in CloudWatch
                  </Button>
                </div>
              </div>
              
              {selectedEnvironmentForVars ? (
                <LogsViewer environmentId={selectedEnvironmentForVars} />
              ) : environments.length === 0 ? (
                <div className="text-center py-12 bg-gray-50 rounded-lg">
                  <p className="text-gray-500">No environments found.</p>
                  <p className="text-sm text-gray-400 mt-1">
                    Create an environment first in the &quot;Deployment Environments&quot; tab.
                  </p>
                </div>
              ) : (
                <div className="text-center py-12 bg-gray-50 rounded-lg">
                  <p className="text-gray-500">Select an environment to view its logs.</p>
                </div>
              )}
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
                      variant={activeSettingsTab === 'repository' ? 'secondary' : 'ghost'}
                      onClick={() => setActiveSettingsTab('environments')}
                      className="w-full justify-start text-sm font-medium"
                    >
                      Deployment Environments
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
                    <div className="space-y-6">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-lg font-medium text-gray-900">Environment Variables</h3>
                          <p className="text-sm text-gray-500">
                            Manage environment-specific variables and secrets for your application.
                          </p>
                        </div>
                        <div className="min-w-[200px]">
                          <Select
                            value={selectedEnvironmentForVars || ''}
                            onValueChange={setSelectedEnvironmentForVars}
                          >
                            <SelectTrigger>
                              <SelectValue placeholder="Select environment" />
                            </SelectTrigger>
                            <SelectContent>
                              {environments.map((env) => (
                                <SelectItem key={env.id} value={env.id}>
                                  {env.name} ({env.branch})
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                      
                      {selectedEnvironmentForVars ? (
                        <EnvironmentVariables environmentId={selectedEnvironmentForVars} />
                      ) : environments.length === 0 ? (
                        <div className="text-center py-12 bg-gray-50 rounded-lg">
                          <p className="text-gray-500">No environments found.</p>
                          <p className="text-sm text-gray-400 mt-1">
                            Create an environment first in the &quot;Deployment Environments&quot; tab.
                          </p>
                        </div>
                      ) : (
                        <div className="text-center py-12 bg-gray-50 rounded-lg">
                          <p className="text-gray-500">Select an environment to manage its variables.</p>
                        </div>
                      )}
                    </div>
                  )}

                  {activeSettingsTab === 'environments' && (
                    <div className="bg-white rounded-lg">
                      <EnvironmentManagement 
                        projectId={project?.id || ''} 
                        teamId={project?.teamId}
                        onEnvironmentSelect={(env) => {
                          setSelectedEnvironment(env)
                          // You could also switch to a deployment tab for that environment
                        }}
                        onEnvironmentChange={fetchEnvironments}
                      />
                    </div>
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
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-lg font-medium text-gray-900">AWS Resources</h3>
                          <p className="text-sm text-gray-500">
                            View environment-specific AWS resources and infrastructure.
                          </p>
                        </div>
                        <div className="min-w-[200px]">
                          <Select
                            value={selectedEnvironmentForVars || ''}
                            onValueChange={setSelectedEnvironmentForVars}
                          >
                            <SelectTrigger>
                              <SelectValue placeholder="Select environment" />
                            </SelectTrigger>
                            <SelectContent>
                              {environments.map((env) => (
                                <SelectItem key={env.id} value={env.id}>
                                  {env.name} ({env.branch})
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      </div>

                      {selectedEnvironmentForVars ? (
                        <div className="space-y-6">
                          <ResourceConfiguration 
                            projectId={params.id as string} 
                            environmentId={selectedEnvironmentForVars}
                            project={project}
                            onUpdate={fetchProject}
                          />
     
                          <NetworkConfiguration 
                            projectId={params.id as string} 
                            environmentId={selectedEnvironmentForVars}
                            project={project}
                            onUpdate={fetchProject}
                          />

                          <div className="bg-white border border-gray-200 rounded-lg p-6">
                            <h2 className="text-xl font-semibold text-gray-900 mb-4">Other Resources</h2>
                            {(() => {
                              const selectedEnv = environments.find(e => e.id === selectedEnvironmentForVars)
                              return selectedEnv ? (
                                <div className="space-y-3">
                                  {selectedEnv.ecsServiceArn && (
                                    <div className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded-lg">
                                      <div>
                                        <span className="text-sm font-medium text-gray-900">ECS Service</span>
                                        <p className="text-xs text-gray-500 truncate max-w-full">{selectedEnv.ecsServiceArn}</p>
                                      </div>
                                    </div>
                                  )}
                                  
                                  {selectedEnv.ecsClusterArn && (
                                    <div className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded-lg">
                                      <div>
                                        <span className="text-sm font-medium text-gray-900">ECS Cluster</span>
                                        <p className="text-xs text-gray-500 truncate max-w-full">{selectedEnv.ecsClusterArn}</p>
                                      </div>
                                    </div>
                                  )}

                                  {selectedEnv.albArn && (
                                    <div className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded-lg">
                                      <div>
                                        <span className="text-sm font-medium text-gray-900">Load Balancer</span>
                                        <p className="text-xs text-gray-500 truncate max-w-full">{selectedEnv.albArn}</p>
                                      </div>
                                    </div>
                                  )}
                                  
                                  <div className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded-lg">
                                    <div>
                                      <span className="text-sm font-medium text-gray-900">Logs</span>
                                      <p className="text-xs text-gray-500">/ecs/{project.name}-{selectedEnv.name}</p>
                                    </div>
                                  </div>
                                  
                                  <div className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded-lg">
                                    <div>
                                      <span className="text-sm font-medium text-gray-900">Container Registry</span>
                                      <p className="text-xs text-gray-500">{project.name.toLowerCase().replace(/[^a-z0-9-_]/g, '-')}-{selectedEnv.name.toLowerCase()}</p>
                                    </div>
                                  </div>

                                  <div className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded-lg">
                                    <div>
                                      <span className="text-sm font-medium text-gray-900">AWS Region</span>
                                      <p className="text-xs text-gray-500">{selectedEnv.awsConfig.region}</p>
                                    </div>
                                  </div>
                                </div>
                              ) : (
                                <div className="text-center py-4">
                                  <p className="text-sm text-gray-500">Environment not found</p>
                                </div>
                              )
                            })()}
                          </div>
                        </div>
                      ) : environments.length === 0 ? (
                        <div className="text-center py-12 bg-gray-50 rounded-lg">
                          <p className="text-gray-500">No environments found.</p>
                          <p className="text-sm text-gray-400 mt-1">
                            Create an environment first in the &quot;Deployment Environments&quot; tab.
                          </p>
                        </div>
                      ) : (
                        <div className="text-center py-12 bg-gray-50 rounded-lg">
                          <p className="text-gray-500">Select an environment to view its AWS resources.</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'shell' && (
            <div className="bg-white shadow rounded-lg p-6">
              <div className="flex justify-between items-center mb-4">
                <div>
                  <h2 className="text-xl font-semibold text-gray-900">Shell Access</h2>
                  <p className="text-sm text-gray-500">
                    Execute commands directly in your deployed application containers.
                  </p>
                </div>
                <div className="min-w-[200px]">
                  <Select
                    value={selectedEnvironmentForVars || ''}
                    onValueChange={setSelectedEnvironmentForVars}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select environment" />
                    </SelectTrigger>
                    <SelectContent>
                      {environments.map((env) => (
                        <SelectItem key={env.id} value={env.id}>
                          {env.name} ({env.branch})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              
              {selectedEnvironmentForVars ? (
                <SimpleShell 
                  environmentId={selectedEnvironmentForVars} 
                  isActive={activeTab === 'shell'} 
                />
              ) : environments.length === 0 ? (
                <div className="text-center py-12 bg-gray-50 rounded-lg">
                  <p className="text-gray-500">No environments found.</p>
                  <p className="text-sm text-gray-400 mt-1">
                    Create an environment first in the &quot;Deployment Environments&quot; tab.
                  </p>
                </div>
              ) : (
                <div className="text-center py-12 bg-gray-50 rounded-lg">
                  <p className="text-gray-500">Select an environment to access its shell.</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Deployment Modal */}
        <DeploymentModal
          projectId={project?.id || ''}
          isOpen={deploymentModalOpen}
          onClose={() => setDeploymentModalOpen(false)}
          onDeploymentStarted={handleDeploymentStarted}
        />
      </div>
    </div>
  )
}