'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { apiClient } from '@/lib/api'
import { Environment, DeploymentStatus } from '@/types'
import { 
  Plus, 
  Settings, 
  Trash2, 
  AlertCircle, 
  CheckCircle, 
  Activity, 
  GitBranch, 
  Server, 
  Globe,
  Cpu,
  MemoryStick
} from 'lucide-react'

interface EnvironmentManagementProps {
  projectId: string
  teamId?: string
  onEnvironmentSelect?: (environment: Environment) => void
  onEnvironmentChange?: () => void
}

export default function EnvironmentManagement({ projectId, teamId, onEnvironmentSelect, onEnvironmentChange }: EnvironmentManagementProps) {
  const [environments, setEnvironments] = useState<Environment[]>([])
  const [availableAwsConfigs, setAvailableAwsConfigs] = useState<Array<{ id: string; name: string; region: string; type: string }>>([])
  const [awsResources, setAwsResources] = useState<{ vpcs: any[]; subnetsByVpc: any; clusters: any[] }>({ vpcs: [], subnetsByVpc: {}, clusters: [] })
  const [loadingAwsResources, setLoadingAwsResources] = useState(false)
  const [loading, setLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isDeleting, setIsDeleting] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editingEnvironment, setEditingEnvironment] = useState<Environment | null>(null)

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    branch: 'main',
    awsConfigId: '',
    existingVpcId: '',
    existingSubnetIds: '',
    existingClusterArn: '',
    cpu: 256,
    memory: 512,
    diskSize: 21,
    port: 3000,
    healthCheckPath: '/health',
    subdirectory: ''
  })
  const [selectedSubnets, setSelectedSubnets] = useState<string[]>([])

  useEffect(() => {
    fetchEnvironments()
  }, [projectId])

  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => setSuccess(''), 5000)
      return () => clearTimeout(timer)
    }
  }, [success])

  const fetchEnvironments = async () => {
    try {
      setLoading(true)
      const data = await apiClient.getProjectEnvironments(projectId)
      setEnvironments(data)
    } catch (error: any) {
      setError('Failed to load environments')
    } finally {
      setLoading(false)
    }
  }

  const fetchAvailableAwsConfigs = async () => {
    try {
      if (!teamId) {
        console.error('No team ID available to fetch AWS configs')
        setAvailableAwsConfigs([])
        return
      }

      // Get team AWS configs
      const configs = await apiClient.getTeamAwsConfigs(teamId)
      
      // Filter to only active configs and transform to expected format
      const activeConfigs = configs
        .filter(config => config.isActive)
        .map(config => ({
          id: config.id,
          name: config.name,
          region: config.awsRegion,
          type: 'team'
        }))
      
      setAvailableAwsConfigs(activeConfigs)
    } catch (error) {
      console.error('Failed to load AWS configs:', error)
      setAvailableAwsConfigs([])
    }
  }

  const fetchAwsResources = async () => {
    try {
      if (!teamId) {
        console.error('No team ID available to fetch AWS resources')
        return
      }

      console.log('Fetching AWS resources for team:', teamId)
      setLoadingAwsResources(true)
      const resources = await apiClient.getAwsResources('team', teamId)
      console.log('AWS resources loaded:', resources)
      setAwsResources(resources)
    } catch (error) {
      console.error('Failed to load AWS resources:', error)
      setAwsResources({ vpcs: [], subnetsByVpc: {}, clusters: [] })
    } finally {
      setLoadingAwsResources(false)
    }
  }

  const openCreateForm = () => {
    setEditingEnvironment(null)
    setFormData({
      name: '',
      branch: 'main',
      awsConfigId: '',
      existingVpcId: '',
      existingSubnetIds: '',
      existingClusterArn: '',
      cpu: 256,
      memory: 512,
      diskSize: 21,
      port: 3000,
      healthCheckPath: '/health',
      subdirectory: ''
    })
    setSelectedSubnets([])
    setShowForm(true)
    fetchAvailableAwsConfigs()
    fetchAwsResources()
  }

  const openEditForm = (environment: Environment) => {
    setEditingEnvironment(environment)
    const subnets = environment.existingSubnetIds ? JSON.parse(environment.existingSubnetIds) : []
    setFormData({
      name: environment.name,
      branch: environment.branch,
      awsConfigId: environment.awsConfig.id,
      existingVpcId: environment.existingVpcId || '',
      existingSubnetIds: subnets.join(','),
      existingClusterArn: environment.existingClusterArn || '',
      cpu: environment.cpu,
      memory: environment.memory,
      diskSize: environment.diskSize || 21,
      port: environment.port,
      healthCheckPath: environment.healthCheckPath,
      subdirectory: environment.subdirectory || ''
    })
    setSelectedSubnets(subnets)
    setShowForm(true)
    fetchAvailableAwsConfigs()
    fetchAwsResources()
    if (environment.id) {
      apiClient.getAvailableAwsConfigs(environment.id).then(data => {
        setAvailableAwsConfigs(data.teamConfigs)
      }).catch(() => {
        // Fallback or show error
      })
    }
  }

  const handleVpcChange = (vpcId: string) => {
    setFormData({ ...formData, existingVpcId: vpcId === "default" ? "" : vpcId })
    setSelectedSubnets([])
  }

  const handleSubnetToggle = (subnetId: string) => {
    const newSelected = selectedSubnets.includes(subnetId)
      ? selectedSubnets.filter(id => id !== subnetId)
      : [...selectedSubnets, subnetId]
    setSelectedSubnets(newSelected)
    setFormData({ ...formData, existingSubnetIds: newSelected.join(',') })
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    setError('')
    setSuccess('')

    try {
      const submitData = {
        name: formData.name,
        branch: formData.branch,
        awsConfigId: formData.awsConfigId,
        awsConfigType: 'team',
        cpu: formData.cpu,
        memory: formData.memory,
        diskSize: formData.diskSize,
        port: formData.port,
        healthCheckPath: formData.healthCheckPath,
        subdirectory: formData.subdirectory || null,
        existingVpcId: formData.existingVpcId || null,
        existingSubnetIds: selectedSubnets.length > 0 ? JSON.stringify(selectedSubnets) : null,
        existingClusterArn: formData.existingClusterArn || null
      }

      if (editingEnvironment) {
        await apiClient.updateEnvironment(editingEnvironment.id, submitData)
        setSuccess(`Environment "${formData.name}" updated successfully`)
      } else {
        await apiClient.createEnvironment(projectId, submitData)
        setSuccess(`Environment "${formData.name}" created successfully`)
      }
      
      setShowForm(false)
      await fetchEnvironments()
      onEnvironmentChange?.()
    } catch (error: any) {
      setError(error.message || 'Failed to save environment')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async (environment: Environment) => {
    if (!confirm(`Are you sure you want to delete the environment "${environment.name}"? This action cannot be undone.`)) {
      return
    }

    setIsDeleting(environment.id)
    setError('')

    try {
      await apiClient.deleteEnvironment(environment.id)
      setSuccess(`Environment "${environment.name}" deleted successfully`)
      await fetchEnvironments()
      onEnvironmentChange?.()
    } catch (error: any) {
      setError(error.message || 'Failed to delete environment')
    } finally {
      setIsDeleting(null)
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

  if (loading) {
    return (
      <div className="text-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
        <p className="text-gray-600 mt-2">Loading environments...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {success && (
        <Alert>
          <CheckCircle className="h-4 w-4" />
          <AlertDescription>{success}</AlertDescription>
        </Alert>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Deployment Environments</h2>
        </div>
        <Button onClick={openCreateForm}>
          <Plus className="h-4 w-4 mr-2" />
          Add Environment
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>
              {editingEnvironment ? 'Edit Environment' : 'Create Environment'}
            </CardTitle>
            <CardDescription>
              {editingEnvironment 
                ? 'Update environment configuration and deployment settings'
                : 'Set up a new environment for deploying your application'
              }
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label>Environment Name</Label>
                  <Input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="e.g., Production, Staging, Development"
                    required
                    className="mt-1"
                  />
                </div>

                <div>
                  <Label>Git Branch</Label>
                  <Input
                    type="text"
                    value={formData.branch}
                    onChange={(e) => setFormData({ ...formData, branch: e.target.value })}
                    placeholder="main"
                    required
                    className="mt-1"
                  />
                </div>
              </div>

              <div>
                <Label>AWS Configuration</Label>
                <Select
                  value={formData.awsConfigId}
                  onValueChange={(value) => setFormData({ ...formData, awsConfigId: value })}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue placeholder="Select AWS configuration" />
                  </SelectTrigger>
                  <SelectContent>
                    {availableAwsConfigs.map((config) => (
                      <SelectItem key={config.id} value={config.id}>
                        {config.name} ({config.region})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {availableAwsConfigs.length === 0 && (
                  <p className="text-sm text-amber-600 mt-1">
                    {!teamId 
                      ? "No team information available. Please refresh the page." 
                      : "No AWS configurations available. Please set up team AWS credentials first."
                    }
                  </p>
                )}
              </div>

              <div className="flex justify-end space-x-2 pt-4">
                <Button type="button" variant="outline" onClick={() => setShowForm(false)}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={isSubmitting || !formData.name || !formData.branch || !formData.awsConfigId}
                >
                  {isSubmitting ? 'Saving...' : editingEnvironment ? 'Update Environment' : 'Create Environment'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {environments.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Server className="h-12 w-12 text-gray-400 mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No Environments</h3>
            <p className="text-gray-500 text-center mb-6 max-w-md">
              Create your first environment to start deploying your application to different stages like production, staging, or development.
            </p>
            <Button onClick={openCreateForm}>
              <Plus className="h-4 w-4 mr-2" />
              Create Your First Environment
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {environments.map((environment) => (
            <Card key={environment.id} className="cursor-pointer hover:shadow-md transition-shadow" onClick={() => onEnvironmentSelect?.(environment)}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <div>
                      <CardTitle className="flex items-center">
                        <Server className="h-5 w-5 mr-2 text-blue-600" />
                        {environment.name}
                      </CardTitle>
                      <CardDescription className="mt-1 flex items-center space-x-4">
                        <span className="flex items-center">
                          <GitBranch className="h-3 w-3 mr-1" />
                          {environment.branch}
                        </span>
                        {environment.domain && (
                          <a 
                            href={`http://${environment.domain}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center text-blue-600 hover:text-blue-800 hover:underline"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <Globe className="h-3 w-3 mr-1" />
                            {environment.domain}
                          </a>
                        )}
                      </CardDescription>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Button 
                      variant="outline" 
                      size="sm" 
                      onClick={(e) => {
                        e.stopPropagation()
                        openEditForm(environment)
                      }}
                    >
                      <Settings className="h-4 w-4 mr-2" />
                      Edit
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDelete(environment)
                      }}
                      disabled={isDeleting === environment.id}
                      className="text-red-600 border-red-300 hover:bg-red-50"
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      {isDeleting === environment.id ? 'Deleting...' : 'Delete'}
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>                
                {environment.latestDeployment && (
                  <div className="mt-4 pt-4 border-t">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-gray-700">Latest Deployment</span>
                      <Badge className={getDeploymentStatusColor(environment.latestDeployment.status)}>
                        {environment.latestDeployment.status.toLowerCase()}
                      </Badge>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">
                      {new Date(environment.latestDeployment.createdAt).toLocaleString()}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}