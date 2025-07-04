'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { apiClient } from '@/lib/api'
import { Environment, DeploymentStatus } from '@/types'
import { 
  X,
  AlertCircle, 
  CheckCircle, 
  Play,
  GitBranch, 
  Server, 
  Globe,
  Cpu,
  MemoryStick,
  Activity
} from 'lucide-react'

interface DeploymentModalProps {
  projectId: string
  isOpen: boolean
  onClose: () => void
  onDeploymentStarted?: (deploymentId: string, environmentId: string) => void
}

export default function DeploymentModal({ projectId, isOpen, onClose, onDeploymentStarted }: DeploymentModalProps) {
  const [environments, setEnvironments] = useState<Environment[]>([])
  const [loading, setLoading] = useState(true)
  const [deploying, setDeploying] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    if (isOpen) {
      fetchEnvironments()
    }
  }, [isOpen, projectId])

  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => setSuccess(''), 5000)
      return () => clearTimeout(timer)
    }
  }, [success])

  const fetchEnvironments = async () => {
    try {
      setLoading(true)
      setError('')
      const data = await apiClient.getProjectEnvironments(projectId)
      setEnvironments(data)
    } catch (error: any) {
      setError('Failed to load environments')
    } finally {
      setLoading(false)
    }
  }

  const handleDeploy = async (environment: Environment) => {
    setDeploying(environment.id)
    setError('')
    setSuccess('')

    try {
      const result = await apiClient.deployEnvironment(environment.id)
      setSuccess(`Deployment started for ${environment.name}`)
      onDeploymentStarted?.(result.deploymentId, environment.id)
      
      // Close modal after a short delay to show success message
      setTimeout(() => {
        onClose()
      }, 2000)
    } catch (error: any) {
      setError(error.message || `Failed to deploy to ${environment.name}`)
    } finally {
      setDeploying(null)
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'DEPLOYED': return 'bg-green-100 text-green-800'
      case 'DEPLOYING': return 'bg-blue-100 text-blue-800'
      case 'FAILED': return 'bg-red-100 text-red-800'
      case 'BUILDING': return 'bg-yellow-100 text-yellow-800'
      default: return 'bg-gray-100 text-gray-800'
    }
  }

  const getDeploymentStatusColor = (status: DeploymentStatus) => {
    switch (status) {
      case DeploymentStatus.SUCCESS: return 'bg-green-100 text-green-800'
      case DeploymentStatus.FAILED: return 'bg-red-100 text-red-800'
      case DeploymentStatus.PENDING:
      case DeploymentStatus.BUILDING:
      case DeploymentStatus.PUSHING:
      case DeploymentStatus.PROVISIONING:
      case DeploymentStatus.DEPLOYING: return 'bg-blue-100 text-blue-800'
      default: return 'bg-gray-100 text-gray-800'
    }
  }

  const isEnvironmentDeploying = (environment: Environment) => {
    return environment.status === 'DEPLOYING' || 
           environment.status === 'BUILDING' ||
           (environment.latestDeployment && 
            [DeploymentStatus.PENDING, DeploymentStatus.BUILDING, DeploymentStatus.PUSHING, 
             DeploymentStatus.PROVISIONING, DeploymentStatus.DEPLOYING].includes(environment.latestDeployment.status))
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-background rounded shadow-lg max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b">
          <div>
            <h2 className="text-lg">Deploy Project</h2>
            <p className="mt-1 text-muted-foreground text-sm">Select an environment to deploy to</p>
          </div>
          <Button variant="outline" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="p-6">
          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {success && (
            <Alert className="mb-4">
              <CheckCircle className="h-4 w-4" />
              <AlertDescription>{success}</AlertDescription>
            </Alert>
          )}

          {loading ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
              <p className="text-gray-600 mt-2">Loading environments...</p>
            </div>
          ) : environments.length === 0 ? (
            <div className="text-center py-8">
              <Server className="h-12 w-12 text-gray-400 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-gray-900 mb-2">No Environments</h3>
              <p className="text-gray-500 mb-4">
                You need to create at least one environment before you can deploy.
              </p>
              <Button onClick={onClose}>
                Close
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="grid gap-4">
                {environments.map((environment) => {
                  const isCurrentlyDeploying = isEnvironmentDeploying(environment)
                  const isThisDeploying = deploying === environment.id
                  
                  return (
                    <Card key={environment.id} className="hover:shadow-md transition-shadow">
                      <CardHeader>
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-3">
                            <div>
                              <CardTitle className="flex items-center">
                                <Server className="h-5 w-5 mr-2 text-blue-600" />
                                {environment.name}
                              </CardTitle>
                            </div>
                          </div>
                          <div className="flex items-center space-x-2">

                            <Button
                              onClick={() => handleDeploy(environment)}
                              disabled={isCurrentlyDeploying || isThisDeploying}
                              size="sm"
                            >
                              <Play className="h-4 w-4 mr-2" />
                              {isThisDeploying ? 'Deploying...' : 
                               isCurrentlyDeploying ? 'Deploying' : 'Deploy'}
                            </Button>
                          </div>
                        </div>
                      </CardHeader>
                      <CardContent>  
                        {environment.latestDeployment && (
                          <div className="mt-4 pt-4 border-t">
                            <div className="flex items-center justify-between">
                              <div>
                              <span className="text-sm font-medium text-muted-foreground">Latest Deployment</span>
                              <span className="text-xs ml-2 mt-1">
                                {new Date(environment.latestDeployment.createdAt).toLocaleString()}
                              </span>
                              </div>
                              <Badge className={getDeploymentStatusColor(environment.latestDeployment.status)}>
                                {environment.latestDeployment.status.toLowerCase()}
                              </Badge>
                            </div>
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}