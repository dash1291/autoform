'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { Spinner } from '@/components/ui/spinner'
import Link from 'next/link'
import { Project, Deployment, Environment } from '@/types'
import LogsViewer from '@/components/LogsViewer'
import EnvironmentVariables from '@/components/EnvironmentVariables'
import EnvironmentManagement from '@/components/EnvironmentManagement'
import DomainManagement from '@/components/DomainManagement'
import DeploymentModal from '@/components/DeploymentModal'
import SimpleShell from '@/components/SimpleShell'
import NetworkConfiguration from '@/components/NetworkConfiguration'
import ResourceConfiguration from '@/components/ResourceConfiguration'
import RepositoryConfiguration from '@/components/RepositoryConfiguration'
import { DeleteProjectDialog } from '@/components/DeleteProjectDialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Clock, GitCommit, Server } from 'lucide-react'
import { useAuth } from '@/lib/auth-client'
import { apiClient } from '@/lib/api'
import { formatToLocalTime, formatDeploymentTime, processDeploymentLogs } from '@/lib/dateUtils'
import TabNavButton from '@/components/TabNavButton'

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
  const [activeSettingsTab, setActiveSettingsTab] = useState<'environment' | 'environments' | 'repository' | 'resources' | 'domains'>('repository')
  const [environments, setEnvironments] = useState<Environment[]>([])
  const [selectedEnvironmentForVars, setSelectedEnvironmentForVars] = useState<string | null>(null)
  const [serviceStatus, setServiceStatus] = useState<any>(null)
  const [awsRegion, setAwsRegion] = useState<string | null>(null)
  const [environmentStatuses, setEnvironmentStatuses] = useState<Record<string, any>>({})
  const [deploymentModalOpen, setDeploymentModalOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)

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
    if (tab) {
      // Handle nested tabs like "settings_environments"
      if (tab.startsWith('settings_')) {
        setActiveTab('settings')
        const settingsSubTab = tab.replace('settings_', '')
        if (['environment', 'environments', 'repository', 'resources', 'domains'].includes(settingsSubTab)) {
          setActiveSettingsTab(settingsSubTab as any)
        }
      } else if (['overview', 'deployments', 'logs', 'settings', 'shell'].includes(tab)) {
        setActiveTab(tab as any)
      }
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

  // Refresh environment statuses periodically
  useEffect(() => {
    if (environments.length > 0) {
      // Refresh environment statuses every 30 seconds
      const interval = setInterval(() => fetchEnvironmentStatuses(environments), 30000)
      return () => clearInterval(interval)
    }
  }, [environments])

  // Poll for live logs when there's an active deployment
  useEffect(() => {
    let interval: NodeJS.Timeout | null = null

    if (activeDeploymentId) {
      // Fetch logs immediately
      fetchLiveLogs(activeDeploymentId)
      
      // Set up polling every 2 seconds
      interval = setInterval(() => {
        fetchLiveLogs(activeDeploymentId)
        fetchDeployments() // Only refresh deployment status - project data is static during deployment
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
      // Fetch AWS region based on project ownership (only on initial load)
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

  const fetchProjectDataOnly = async () => {
    try {
      const data = await apiClient.getProject(params.id as string)
      setProject(data)
    } catch (err: any) {
      console.error('Failed to fetch project data:', err)
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
      // Fetch service status for each environment
      fetchEnvironmentStatuses(data)
    } catch (err) {
      console.error('Failed to fetch environments:', err)
    }
  }

  const fetchEnvironmentStatuses = async (envs: Environment[]) => {
    try {
      const statusPromises = envs.map(async (env) => {
        try {
          const status = await apiClient.getEnvironmentServiceStatus(env.id)
          return { [env.id]: status }
        } catch (err) {
          console.error(`Failed to fetch status for environment ${env.id}:`, err)
          return { [env.id]: { status: 'ERROR', message: 'Failed to fetch status' } }
        }
      })
      
      const statuses = await Promise.all(statusPromises)
      const statusMap = statuses.reduce((acc, status) => ({ ...acc, ...status }), {})
      setEnvironmentStatuses(statusMap)
    } catch (err) {
      console.error('Failed to fetch environment statuses:', err)
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
    fetchProjectDataOnly()
    fetchDeployments()
  }

  const handleAbortDeployment = async (deploymentId: string) => {
    if (!confirm('Are you sure you want to abort this deployment?')) return
    
    try {
      await apiClient.abortDeployment(deploymentId)
      // Refresh project and deployments
      fetchProjectDataOnly()
      fetchDeployments()
    } catch (err) {
      setError('Failed to abort deployment')
    }
  }

  const handleDelete = () => {
    setDeleteDialogOpen(true)
  }

  const handleDeleteSuccess = () => {
    router.push('/dashboard')
  }

  if (!authLoading && !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
        <h1 className="text-xl font-semibold mb-4">Please sign in</h1>
        <p className="text-muted-foreground">You need to be signed in to view this project.</p>
        </div>
      </div>
    )
  }

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Spinner />
      </div>
    )
  }

  if (error || !project) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-foreground mb-4">Project Not Found</h1>
          <p className="text-muted-foreground mb-4">{error || 'The project you are looking for does not exist.'}</p>
          <Link
            href="/dashboard"
            className="bg-primary text-white px-4 py-2 rounded-lg hover:bg-primary transition-colors"
          >
            Back to Dashboard
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div>
              <Link
                href="/dashboard"
                className="text-muted-foreground text-xs hover:text-foreground mb-2 inline-block"
              >
                ← Back to Dashboard
              </Link>
              <h1 className="text-xl font-normal">{project.name}</h1>
              <p className="text-sm">{project.gitRepoUrl}</p>
            </div>
            {/* Status is now at environment level */}
          </div>
        </div>

        {/* Tabs */}
        <div className="mb-6">
          <div className="border-b pb-0.5">
            <nav className="-mb-px flex space-x-8">
              <TabNavButton
                active={activeTab === 'overview'}
                onClick={() => setActiveTab('overview')}
              >
                Overview
              </TabNavButton>
              <TabNavButton
                active={activeTab === 'deployments'}
                onClick={() => setActiveTab('deployments')}
              >
                Deployments ({deployments.length})
              </TabNavButton>
              <TabNavButton
                active={activeTab === 'logs'}
                onClick={() => setActiveTab('logs')}
              >
                Application Logs
              </TabNavButton>
              <TabNavButton
                active={activeTab === 'shell'}
                onClick={() => setActiveTab('shell')}
              >
                Shell Access
              </TabNavButton>
              <TabNavButton
                active={activeTab === 'settings'}
                onClick={() => setActiveTab('settings')}
              >
                Settings
              </TabNavButton>
            </nav>
          </div>
        </div>

        <div className="space-y-6">
          {activeTab === 'overview' && (
            <>
              {/* Environment Status Cards */}
              <div className="shadow rounded-lg p-6">
                <h2 className="text-lg mb-4">Environment Status</h2>
                {environments.length === 0 ? (
                  <div className="py-8 rounded-lg">
                    <p>No environments configured for this project.</p>
                    <p className="text-sm text-muted-foreground mt-1">
                      Create an environment in the Settings tab to start deploying.
                    </p>
                  </div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {environments.map((env) => {
                      const envStatus = environmentStatuses[env.id]
                      return (
                        <div key={env.id} className="border border-border rounded-lg p-4">
                          <div className="flex items-center justify-between mb-3">
                            <div>
                              <h3 className="font-medium text-foreground">{env.name}</h3>
                              <p className="text-sm text-muted-foreground">{env.branch}</p>
                            </div>
                            <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                              envStatus?.status === 'HEALTHY' ? 'text-success-foreground' :
                              envStatus?.status === 'CRASH_LOOP' ? 'bg-destructive/20 text-destructive' :
                              envStatus?.status === 'IN_PROGRESS' ? 'bg-primary/20 text-primary' :
                              envStatus?.status === 'DEGRADED' ? 'bg-accent/20 text-accent-foreground' :
                              envStatus?.status === 'NO_RUNNING_TASKS' ? 'bg-primary text-foreground' :
                              envStatus?.status === 'NOT_DEPLOYED' ? 'bg-primary text-muted-foreground' :
                              envStatus?.status === 'ERROR' ? 'bg-destructive/20 text-destructive' :
                              'bg-muted text-foreground'
                            }`}>
                              {envStatus?.status || 'Loading...'}
                            </span>
                          </div>
                          
                          {envStatus && (
                            <div className="space-y-2">
                              <p className="text-sm text-muted-foreground">{envStatus.message}</p>
                              
                              {envStatus.service && (
                                <div className="text-xs text-muted-foreground">
                                  Tasks: {envStatus.service.runningCount}/{envStatus.service.desiredCount} running
                                  {envStatus.service.pendingCount > 0 && ` (${envStatus.service.pendingCount} pending)`}
                                </div>
                              )}
                              
                              {env.domain && (
                                <div className="mt-2">
                                  <a
                                    href={`http://${env.domain}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-xs text-muted-foreground hover:text-foreground underline"
                                  >
                                    {env.domain}
                                  </a>
                                </div>
                              )}
                              
                              {envStatus.crashLoopDetected && (
                                <div className="mt-2 p-2 bg-destructive/20 border border-destructive rounded text-xs text-destructive">
                                  ⚠️ Crash loop detected
                                </div>
                              )}
                              
                              {envStatus.failureReasons && envStatus.failureReasons.length > 0 && (
                                <div className="mt-2 p-2 bg-accent/20 border border-accent rounded">
                                  <p className="text-xs font-medium text-accent-foreground">Issues:</p>
                                  <ul className="text-xs text-accent-foreground mt-1 space-y-1">
                                    {envStatus.failureReasons.slice(0, 2).map((reason: string, index: number) => (
                                      <li key={index}>• {reason}</li>
                                    ))}
                                    {envStatus.failureReasons.length > 2 && (
                                      <li>• +{envStatus.failureReasons.length - 2} more issues</li>
                                    )}
                                  </ul>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              {/* Project Information */}
              <div className="shadow rounded-lg p-6">
                <h2 className="text-lg text-foreground mb-4">Project Information</h2>
                <div className="space-y-4">
                  <div>
                    <span className="text-sm font-medium text-muted-foreground">Repository</span>
                    <div className="mt-1 text-sm text-foreground">{project.gitRepoUrl}</div>
                  </div>
                  
                  <div>
                    <span className="text-sm font-medium text-muted-foreground">Created</span>
                    <div className="mt-1 text-sm text-foreground">
                      {formatToLocalTime(project.createdAt)}
                    </div>
                  </div>
                  
                  <div>
                    <span className="text-sm font-medium text-muted-foreground">Last Updated</span>
                    <div className="mt-1 text-sm text-foreground">
                      {formatToLocalTime(project.updatedAt)}
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}

          {activeTab === 'deployments' && (
            <div className="shadow rounded-lg p-6">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg text-foreground">Deployment History</h2>
                <Button size="sm" onClick={handleDeploy}>
                  Deploy
                </Button>
              </div>
              {deployments.length === 0 ? (
                <p className="text-muted-foreground text-sm">No deployments yet</p>
              ) : (
                <div className="space-y-4">
                  {deployments.map((deployment) => (
                    <div key={deployment.id} className="border border-border rounded-lg p-4">
                      <div className="flex items-center justify-between">
                        <div className="flex text-sm items-center space-x-3">
                          <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded ${
                            deployment.status === 'SUCCESS' ? 'bg-success text-success-foreground':
                            deployment.status === 'FAILED' ? 'bg-destructive' :
                            'bg-accent/20 text-accent-foreground'
                          }`}>
                            {deployment.status}
                          </span>
                          <div className="flex items-center space-x-1">
                            <Server className="h-3 w-3 text-muted-foreground" />
                            <span>{deployment.environment?.name || 'Unknown'}</span>
                          </div>
                          <div className="flex items-center space-x-1">
                            <GitCommit className="h-3 w-3 text-muted-foreground" />
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
                                    className="text-sm bg-muted px-2 py-1 rounded hover:underline"
                                  >
                                    {deployment.commitSha.substring(0, 8)}
                                  </a>
                                ) : (
                                  <code className="text-sm bg-muted px-2 py-1 rounded">{deployment.commitSha.substring(0, 8)}</code>
                                )
                              })()
                            ) : (
                              <code className="text-sm bg-muted px-2 py-1 rounded">N/A</code>
                            )}
                          </div>
                          <div className="flex items-center space-x-1">
                            <Clock className="h-3 w-3 text-muted-foreground" />
                            <span className="text-sm text-muted-foreground">
                              {formatDeploymentTime(deployment.createdAt)}
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
                            <summary className="cursor-pointer text-muted-foreground hover:text-foreground font-medium">
                            View Deployment Logs
                            </summary>
                            <pre className="mt-2 bg-gray-900 text-foreground p-3 rounded text-xs overflow-y-auto max-h-48 whitespace-pre-wrap break-words font-mono">
                              {processDeploymentLogs(deployment.logs)}
                            </pre>
                          </details>
                        </div>
                      ) : (
                        <div className="mt-3 text-sm text-muted-foreground">
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
            <div className="shadow rounded-lg p-6">
              <div className="flex justify-between items-center mb-4">
                <div>
                  <h2 className="text-lg text-foreground">Application Logs</h2>
                  <p className="text-sm text-muted-foreground">
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
                <div className="text-center py-12 bg-primary rounded-lg">
                  <p className="text-muted-foreground">No environments found.</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    Create an environment first in the &quot;Deployment Environments&quot; tab.
                  </p>
                </div>
              ) : (
                <div className="text-center py-12 bg-muted rounded-lg">
                  <p className="text-muted-foreground">Select an environment to view its logs.</p>
                </div>
              )}
            </div>
          )}

          {activeTab === 'settings' && (
            <div className="shadow rounded-lg overflow-hidden">
              <div className="flex">
                {/* Vertical sidebar navigation */}
                <div className="w-64 border-r">
                  <nav className="p-4 space-y-2">
                    <Button
                      variant={'ghost'}
                      onClick={() => setActiveSettingsTab('repository')}
                      className={`${activeSettingsTab === 'repository' ? 'text-foreground' : 'text-muted-foreground'} hover:text-foreground w-full justify-start text-sm`}
                    >
                      Git Repository
                    </Button>
                    <Button
                      variant={'ghost'}
                      onClick={() => setActiveSettingsTab('environments')}
                      className={`${activeSettingsTab === 'environments' ? 'text-foreground' : 'text-muted-foreground'} hover:text-foreground w-full justify-start text-sm`}
                    >
                      Environments
                    </Button>
                    <Button
                      variant={'ghost'}
                      onClick={() => setActiveSettingsTab('environment')}
                      className={`${activeSettingsTab === 'environment' ? 'text-foreground' : 'text-muted-foreground'} hover:text-foreground w-full justify-start text-sm`}
                    >
                      Environment Variables
                    </Button>
                    <Button
                      variant={'ghost'}
                      onClick={() => setActiveSettingsTab('domains')}
                      className={`${activeSettingsTab === 'domains' ? 'text-foreground' : 'text-muted-foreground'} hover:text-foreground w-full justify-start text-sm`}
                    >
                      Domains
                    </Button>
                    <Button
                      variant={'ghost'}
                      onClick={() => setActiveSettingsTab('resources')}
                      className={`${activeSettingsTab === 'resources' ? 'text-foreground' : 'text-muted-foreground'} hover:text-foreground w-full justify-start text-sm`}
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
                          <h3 className="text-lg font-medium text-foreground">Environment Variables</h3>
                          <p className="text-sm text-muted-foreground">
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
                        <div className="text-center py-12 rounded-lg">
                          <p className="text-muted-foreground">No environments found.</p>
                          <p className="text-sm text-muted-foreground mt-1">
                            Create an environment first in the &quot;Deployment Environments&quot; tab.
                          </p>
                        </div>
                      ) : (
                        <div className="text-center py-12 bg-muted rounded-lg">
                          <p className="text-muted-foreground">Select an environment to manage its variables.</p>
                        </div>
                      )}
                    </div>
                  )}
                  {activeSettingsTab === 'environments' && (
                    <div className="rounded-lg">
                      <EnvironmentManagement
                        projectId={project?.id || ''}
                        teamId={project?.teamId}
                        onEnvironmentSelect={(env) => {
                          setSelectedEnvironment(env)
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
                  {activeSettingsTab === 'domains' && (
                    <DomainManagement
                      projectId={project?.id || ''}
                      teamId={project?.teamId}
                    />
                  )}
                  {activeSettingsTab === 'resources' && (
                    <div className="space-y-6">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-lg font-medium text-foreground">AWS Resources</h3>
                          <p className="text-sm text-muted-foreground">
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
                          <div className="border border-border rounded-lg p-6">
                            <h2 className="text-md text-foreground mb-4">Other Resources</h2>
                            {(() => {
                              const selectedEnv = environments.find(e => e.id === selectedEnvironmentForVars)
                              return selectedEnv ? (
                                <div className="space-y-3">
                                  {selectedEnv.ecsServiceArn && (
                                    <div className="flex items-center justify-between py-2 px-3 bg-muted rounded-lg">
                                      <div>
                                        <span className="text-sm font-medium text-foreground">ECS Service</span>
                                        <p className="text-xs text-muted-foreground truncate max-w-full">{selectedEnv.ecsServiceArn}</p>
                                      </div>
                                    </div>
                                  )}
                                  {selectedEnv.ecsClusterArn && (
                                    <div className="flex items-center justify-between py-2 px-3 bg-muted rounded-lg">
                                      <div>
                                        <span className="text-sm font-medium text-foreground">ECS Cluster</span>
                                        <p className="text-xs text-muted-foreground truncate max-w-full">{selectedEnv.ecsClusterArn}</p>
                                      </div>
                                    </div>
                                  )}
                                  {selectedEnv.albArn && (
                                    <div className="flex items-center justify-between py-2 px-3 bg-muted rounded-lg">
                                      <div>
                                        <span className="text-sm font-medium text-foreground">Load Balancer</span>
                                        <p className="text-xs text-muted-foreground truncate max-w-full">{selectedEnv.albArn}</p>
                                      </div>
                                    </div>
                                  )}
                                  <div className="flex items-center justify-between py-2 px-3 bg-primary rounded">
                                    <div>
                                      <span className="text-sm font-medium text-foreground">Logs</span>
                                      <p className="text-xs text-muted-foreground">/ecs/{project.name}-{selectedEnv.name}</p>
                                    </div>
                                  </div>
                                  <div className="flex items-center justify-between py-2 px-3 bg-primary rounded-lg">
                                    <div>
                                      <span className="text-sm font-medium text-foreground">Container Registry</span>
                                      <p className="text-xs text-muted-foreground">{project.name.toLowerCase().replace(/[^a-z0-9-_]/g, '-')}-{selectedEnv.name.toLowerCase()}</p>
                                    </div>
                                  </div>
                                  <div className="flex items-center justify-between py-2 px-3 bg-primary rounded-lg">
                                    <div>
                                      <span className="text-sm font-medium text-foreground">AWS Region</span>
                                      <p className="text-xs text-muted-foreground">{selectedEnv.awsConfig.region}</p>
                                    </div>
                                  </div>
                                </div>
                              ) : (
                                <div className="text-center py-4">
                                  <p className="text-sm text-muted-foreground">Environment not found</p>
                                </div>
                              )
                            })()}
                          </div>
                        </div>
                      ) : environments.length === 0 ? (
                        <div className="text-center py-12 rounded-lg">
                          <p className="text-muted-foreground">No environments found.</p>
                          <p className="text-sm text-muted-foreground mt-1">
                            Create an environment first in the &quot;Deployment Environments&quot; tab.
                          </p>
                        </div>
                      ) : (
                        <div className="text-center py-12 bg-muted rounded-lg">
                          <p className="text-muted-foreground">Select an environment to view its AWS resources.</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'shell' && (
            <div className="shadow rounded-lg p-6">
              <div className="flex justify-between items-center mb-4">
                <div>
                  <h2 className="text-lg text-foreground">Shell Access</h2>
                  <p className="text-sm text-muted-foreground">
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
                <div className="text-center py-12 rounded-lg">
                  <p className="text-muted-foreground">No environments found.</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    Create an environment first in the &quot;Deployment Environments&quot; tab.
                  </p>
                </div>
              ) : (
                <div className="text-center py-12 bg-muted rounded-lg">
                  <p className="text-muted-foreground">Select an environment to access its shell.</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      {/* Deployment Modal */}
      <DeploymentModal
        projectId={project?.id || ''}
        isOpen={deploymentModalOpen}
        onClose={() => setDeploymentModalOpen(false)}
        onDeploymentStarted={handleDeploymentStarted}
      />
      
      {/* Delete Project Dialog */}
      {project && (
        <DeleteProjectDialog
          isOpen={deleteDialogOpen}
          onClose={() => setDeleteDialogOpen(false)}
          projectId={project.id}
          projectName={project.name}
          onSuccess={handleDeleteSuccess}
        />
      )}
    </div>
  )
}