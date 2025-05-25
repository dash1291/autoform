'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { Project, Deployment } from '@/types'

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

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Project Info */}
          <div className="lg:col-span-2 space-y-6">
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

            {/* Deployments */}
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
                            <summary className="cursor-pointer text-gray-600">View Logs</summary>
                            <pre className="mt-2 bg-gray-50 p-3 rounded text-xs overflow-auto">
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
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* AWS Resources */}
            <div className="bg-white shadow rounded-lg p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">AWS Resources</h3>
              <div className="space-y-3 text-sm">
                {project.ecsClusterArn && (
                  <div>
                    <span className="font-medium text-gray-500">ECS Cluster:</span>
                    <p className="text-gray-900 break-all">{project.ecsClusterArn}</p>
                  </div>
                )}
                {project.ecsServiceArn && (
                  <div>
                    <span className="font-medium text-gray-500">ECS Service:</span>
                    <p className="text-gray-900 break-all">{project.ecsServiceArn}</p>
                  </div>
                )}
                {project.albArn && (
                  <div>
                    <span className="font-medium text-gray-500">Load Balancer:</span>
                    <p className="text-gray-900 break-all">{project.albArn}</p>
                  </div>
                )}
              </div>
            </div>

            {/* Repository Info */}
            <div className="bg-white shadow rounded-lg p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Repository</h3>
              <div className="space-y-3">
                <a
                  href={project.gitRepoUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:text-blue-700 text-sm break-all"
                >
                  {project.gitRepoUrl}
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}