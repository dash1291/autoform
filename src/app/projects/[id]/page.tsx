'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { Project, Deployment } from '@/types'
import LogsViewer from '@/components/LogsViewer'
import EnvironmentVariables from '@/components/EnvironmentVariables'
import SimpleShell from '@/components/SimpleShell'
import NetworkConfiguration from '@/components/NetworkConfiguration'
import ResourceConfiguration from '@/components/ResourceConfiguration'

export default function ProjectDetail() {
  const { data: session } = useSession()
  const params = useParams()
  const router = useRouter()
  const [project, setProject] = useState<Project | null>(null)
  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [liveLogs, setLiveLogs] = useState<string>('')
  const [activeDeploymentId, setActiveDeploymentId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'overview' | 'deployments' | 'logs' | 'environment' | 'resources' | 'shell'>('overview')

  useEffect(() => {
    if (session && params.id) {
      fetchProject()
      fetchDeployments()
    }
  }, [session, params.id])

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
      const response = await fetch(`/api/projects/${params.id}`)
      if (response.ok) {
        const data = await response.json()
        setProject(data)
      } else if (response.status === 404) {
        setError('Project not found')
      } else {
        setError('Failed to fetch project')
      }
    } catch (err) {
      setError('Failed to fetch project')
    } finally {
      setLoading(false)
    }
  }

  const fetchDeployments = async () => {
    try {
      const response = await fetch(`/api/projects/${params.id}/deployments`)
      if (response.ok) {
        const data = await response.json()
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
      }
    } catch (err) {
      console.error('Failed to fetch deployments:', err)
    }
  }

  const fetchLiveLogs = async (deploymentId: string) => {
    try {
      const response = await fetch(`/api/deployments/${deploymentId}/logs`)
      if (response.ok) {
        const data = await response.json()
        setLiveLogs(data.logs || '')
      }
    } catch (err) {
      console.error('Failed to fetch live logs:', err)
    }
  }

  const handleDeploy = async () => {
    if (!project) return
    
    try {
      const response = await fetch(`/api/projects/${project.id}/deploy`, {
        method: 'POST',
      })
      
      if (response.ok) {
        // Refresh project and deployments
        fetchProject()
        fetchDeployments()
      } else {
        setError('Failed to start deployment')
      }
    } catch (err) {
      setError('Failed to start deployment')
    }
  }

  const handleAbortDeployment = async () => {
    if (!project || !confirm('Are you sure you want to abort the current deployment?')) return
    
    try {
      const response = await fetch(`/api/projects/${project.id}/abort`, {
        method: 'POST',
      })
      
      if (response.ok) {
        // Refresh project and deployments
        fetchProject()
        fetchDeployments()
      } else {
        setError('Failed to abort deployment')
      }
    } catch (err) {
      setError('Failed to abort deployment')
    }
  }

  const handleDelete = async () => {
    if (!project || !confirm('Are you sure you want to delete this project?')) return
    
    try {
      const response = await fetch(`/api/projects/${project.id}`, {
        method: 'DELETE',
      })
      
      if (response.ok) {
        router.push('/dashboard')
      } else {
        setError('Failed to delete project')
      }
    } catch (err) {
      setError('Failed to delete project')
    }
  }

  if (!session) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Please sign in</h1>
          <p className="text-gray-600">You need to be signed in to view this project.</p>
        </div>
      </div>
    )
  }

  if (loading) {
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
            <div className="flex space-x-3">
              {project.status === 'DEPLOYING' || project.status === 'BUILDING' || project.status === 'CLONING' ? (
                <>
                  <button
                    disabled
                    className="bg-gray-400 text-white px-4 py-2 rounded-lg cursor-not-allowed"
                  >
                    {project.status === 'DEPLOYING' ? 'Deploying...' : 
                     project.status === 'BUILDING' ? 'Building...' : 
                     'Cloning...'}
                  </button>
                  <button
                    onClick={handleAbortDeployment}
                    className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 transition-colors"
                  >
                    Abort Deployment
                  </button>
                </>
              ) : (
                <button
                  onClick={handleDeploy}
                  className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
                >
                  Deploy
                </button>
              )}
              <button
                onClick={handleDelete}
                disabled={project.status === 'DEPLOYING' || project.status === 'BUILDING' || project.status === 'CLONING'}
                className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="mb-6">
          <div className="border-b border-gray-200">
            <nav className="-mb-px flex space-x-8">
              <button
                onClick={() => setActiveTab('overview')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'overview'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Overview
              </button>
              <button
                onClick={() => setActiveTab('deployments')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'deployments'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Deployments ({deployments.length})
              </button>
              <button
                onClick={() => setActiveTab('logs')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'logs'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Application Logs
              </button>
              <button
                onClick={() => setActiveTab('environment')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'environment'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Environment
              </button>
              <button
                onClick={() => setActiveTab('resources')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'resources'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                AWS Resources
              </button>
              <button
                onClick={() => setActiveTab('shell')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'shell'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                Shell Access
              </button>
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
              <h2 className="text-xl font-semibold text-gray-900 mb-4">Deployment History</h2>
              {deployments.length === 0 ? (
                <p className="text-gray-500">No deployments yet.</p>
              ) : (
                <div className="space-y-4">
                  {deployments.map((deployment) => (
                    <div key={deployment.id} className="border border-gray-200 rounded-lg p-4">
                      <div className="flex justify-between items-start">
                        <div>
                          <div className="flex items-center space-x-2">
                            <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                              deployment.status === 'SUCCESS' ? 'bg-green-100 text-green-800' :
                              deployment.status === 'FAILED' ? 'bg-red-100 text-red-800' :
                              'bg-yellow-100 text-yellow-800'
                            }`}>
                              {deployment.status}
                            </span>
                            <code className="text-sm bg-gray-100 px-2 py-1 rounded">
                              {deployment.commitSha.substring(0, 8)}
                            </code>
                          </div>
                          <p className="text-sm text-gray-600 mt-1">
                            {new Date(deployment.createdAt).toLocaleString()}
                          </p>
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

          {activeTab === 'environment' && (
            <div className="bg-white shadow rounded-lg p-6">
              <EnvironmentVariables projectId={params.id as string} />
            </div>
          )}

          {activeTab === 'resources' && (
            <>
              <div className="bg-white shadow rounded-lg p-6">
                <ResourceConfiguration 
                  projectId={params.id as string} 
                  project={project}
                  onUpdate={fetchProject}
                />
              </div>
              <div className="bg-white shadow rounded-lg p-6">
                <NetworkConfiguration 
                  projectId={params.id as string} 
                  project={project}
                  onUpdate={fetchProject}
                />
              </div>
              <div className="bg-white shadow rounded-lg p-6">
                <h2 className="text-xl font-semibold text-gray-900 mb-4">Current AWS Resources</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {project.ecsClusterArn && (
                    <div className="border border-gray-200 rounded-lg p-4">
                      <h3 className="font-medium text-gray-900 mb-2">ECS Cluster</h3>
                      <p className="text-sm text-gray-600 break-all">{project.ecsClusterArn}</p>
                      <div className="mt-2">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                          Active
                        </span>
                      </div>
                    </div>
                  )}
                  
                  {project.ecsServiceArn && (
                    <div className="border border-gray-200 rounded-lg p-4">
                      <h3 className="font-medium text-gray-900 mb-2">ECS Service</h3>
                      <p className="text-sm text-gray-600 break-all">{project.ecsServiceArn}</p>
                      <div className="mt-2">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                          Running
                        </span>
                      </div>
                    </div>
                  )}
                  
                  {project.albArn && (
                    <div className="border border-gray-200 rounded-lg p-4">
                      <h3 className="font-medium text-gray-900 mb-2">Application Load Balancer</h3>
                      <p className="text-sm text-gray-600 break-all">{project.albArn}</p>
                      <div className="mt-2">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                          Active
                        </span>
                      </div>
                    </div>
                  )}
                  
                  <div className="border border-gray-200 rounded-lg p-4">
                    <h3 className="font-medium text-gray-900 mb-2">CloudWatch Log Group</h3>
                    <p className="text-sm text-gray-600">/ecs/{project.name}</p>
                    <div className="mt-2">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                        7 Day Retention
                      </span>
                    </div>
                  </div>
                  
                  <div className="border border-gray-200 rounded-lg p-4">
                    <h3 className="font-medium text-gray-900 mb-2">ECR Repository</h3>
                    <p className="text-sm text-gray-600">{project.name.toLowerCase().replace(/[^a-z0-9-_]/g, '-')}</p>
                    <div className="mt-2">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                        Container Registry
                      </span>
                    </div>
                  </div>

                  <div className="border border-gray-200 rounded-lg p-4">
                    <h3 className="font-medium text-gray-900 mb-2">Repository</h3>
                    <a
                      href={project.gitRepoUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-blue-600 hover:text-blue-700 break-all"
                    >
                      {project.gitRepoUrl}
                    </a>
                    <div className="mt-2">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                        Branch: {project.branch}
                      </span>
                    </div>
                  </div>
                </div>

                {!project.ecsClusterArn && !project.ecsServiceArn && !project.albArn && (
                  <div className="text-center py-8">
                    <p className="text-gray-500">No AWS resources found. Deploy your project to see resources here.</p>
                  </div>
                )}
              </div>
            </>
          )}

          {activeTab === 'shell' && (
            <div className="bg-white shadow rounded-lg p-6">
              <SimpleShell projectId={params.id as string} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}