'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { apiClient } from '@/lib/api'

interface NetworkConfigurationProps {
  projectId: string
  environmentId?: string
  project: any
  onUpdate: () => void
}

export default function NetworkConfiguration({ projectId, environmentId, project, onUpdate }: NetworkConfigurationProps) {
  // If environmentId is provided, we need to load and configure that environment's network settings
  const [environment, setEnvironment] = useState<any>(null)
  const [loadingEnv, setLoadingEnv] = useState(false)

  useEffect(() => {
    if (environmentId) {
      fetchEnvironment()
    }
  }, [environmentId])

  const fetchEnvironment = async () => {
    if (!environmentId) return
    setLoadingEnv(true)
    try {
      const envData = await apiClient.getEnvironment(environmentId)
      setEnvironment(envData)
      const subnets = envData.existingSubnetIds ? JSON.parse(envData.existingSubnetIds) : []
      setFormData({
        existingVpcId: envData.existingVpcId || '',
        existingSubnetIds: subnets.join(','),
        existingClusterArn: envData.existingClusterArn || ''
      })
      setSelectedSubnets(subnets)
    } catch (error) {
      console.error('Failed to fetch environment:', error)
    } finally {
      setLoadingEnv(false)
    }
  }

  const isDeployed = project?.status === 'DEPLOYED' || project?.ecsServiceArn || project?.albArn || environment?.status === 'DEPLOYED' || environment?.ecsServiceArn
  const isReadOnly = isDeployed
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [formData, setFormData] = useState({
    existingVpcId: '',
    existingSubnetIds: '',
    existingClusterArn: ''
  })
  const [awsResources, setAwsResources] = useState<any>(null)
  const [deployedResources, setDeployedResources] = useState<any>(null)
  const [loadingResources, setLoadingResources] = useState(false)
  const [selectedSubnets, setSelectedSubnets] = useState<string[]>([])
  const [showTips, setShowTips] = useState(false)

  useEffect(() => {
    if (project) {
      const subnets = project.existingSubnetIds ? JSON.parse(project.existingSubnetIds) : []
      setFormData({
        existingVpcId: project.existingVpcId || '',
        existingSubnetIds: subnets.join(','),
        existingClusterArn: project.existingClusterArn || ''
      })
      setSelectedSubnets(subnets)
    }
  }, [project])

  useEffect(() => {
    if (isReadOnly) {
      fetchDeployedResources()
    } else {
      fetchAwsResources()
    }
  }, [isReadOnly, projectId])

  const fetchAwsResources = async () => {
    setLoadingResources(true)
    try {
      // Use appropriate credentials based on project type
      const credentialType = project?.teamId ? 'team' : 'personal'
      const teamId = project?.teamId || undefined
      const data = await apiClient.getAwsResources(credentialType, teamId)
      setAwsResources(data)
    } catch (err) {
      console.error('Failed to fetch AWS resources:', err)
    } finally {
      setLoadingResources(false)
    }
  }

  const fetchDeployedResources = async () => {
    setLoadingResources(true)
    try {
      const data = await apiClient.getProjectDeployedResources(projectId)
      setDeployedResources(data)
    } catch (err) {
      console.error('Failed to fetch deployed resources:', err)
    } finally {
      setLoadingResources(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (isReadOnly) {
      setError('Network configuration cannot be changed for deployed projects/environments')
      return
    }
    
    setLoading(true)
    setError('')
    setSuccess('')

    try {
      const payload = {
        existingVpcId: formData.existingVpcId || null,
        existingSubnetIds: selectedSubnets.length > 0 ? JSON.stringify(selectedSubnets) : null,
        existingClusterArn: formData.existingClusterArn || null
      }

      if (environmentId) {
        // Update environment network settings
        await apiClient.updateEnvironment(environmentId, payload)
        setSuccess('Environment network configuration updated successfully!')
        await fetchEnvironment() // Refresh environment data
      } else {
        // Update project network settings (legacy)
        await apiClient.updateProject(projectId, payload)
        setSuccess('Network configuration updated successfully!')
      }
      onUpdate()
      setTimeout(() => setSuccess(''), 3000)
    } catch (err: any) {
      setError(err.message || 'Failed to update network configuration')
    } finally {
      setLoading(false)
    }
  }

  const handleClear = () => {
    setFormData({
      existingVpcId: '',
      existingSubnetIds: '',
      existingClusterArn: ''
    })
    setSelectedSubnets([])
  }


  const handleVpcChange = (vpcId: string) => {
    const actualVpcId = vpcId === "create-new" ? "" : vpcId
    setFormData({ ...formData, existingVpcId: actualVpcId })
    setSelectedSubnets([])
  }

  const handleSubnetToggle = (subnetId: string) => {
    const newSelected = selectedSubnets.includes(subnetId)
      ? selectedSubnets.filter(id => id !== subnetId)
      : [...selectedSubnets, subnetId]
    setSelectedSubnets(newSelected)
    setFormData({ ...formData, existingSubnetIds: newSelected.join(',') })
  }

  const availableSubnets = formData.existingVpcId && awsResources?.subnetsByVpc
    ? awsResources.subnetsByVpc[formData.existingVpcId] || []
    : []

  return (
    <Card>
      <CardHeader>
        <CardTitle>Network Configuration</CardTitle>
        <CardDescription>
          Configure existing AWS network resources to use instead of creating new ones. Leave fields empty to create new resources automatically.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isReadOnly && (
          <div className="border text-muted-foreground border-border rounded-lg p-4 mb-4">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <h4 className="text-sm font-medium">Network Configuration Locked</h4>
                <div className="mt-1 text-sm">
                  <p>This project has been deployed and network settings are now read-only. To use different network settings, create a new project.</p>
                </div>
              </div>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">
              {isReadOnly ? 'Assigned VPC' : 'Existing VPC'}
            </label>
            {isReadOnly ? (
              <div className="w-full px-3 py-2 border border-border rounded-lg">
                {loadingResources ? (
                  <div className="flex items-center space-x-2">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                    <span className="text-sm text-gray-600">Loading VPC details...</span>
                  </div>
                ) : deployedResources?.vpc ? (
                  <div className="flex space-x-2">
                    <div>
                      <span className="text-sm font-medium">{deployedResources.vpc.name}</span>
                      <span className="text-xs block">{deployedResources.vpc.id} ({deployedResources.vpc.cidrBlock})</span>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center space-x-2">
                    <svg className="h-4 w-4 text-amber-500" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                    <span className="text-sm">VPC details not available</span>
                  </div>
                )}
              </div>
            ) : loadingResources ? (
              <div className="w-full px-3 py-2 border border-border rounded-lg text-gray-500">
                Loading VPCs...
              </div>
            ) : (
              <Select value={formData.existingVpcId || "create-new"} onValueChange={handleVpcChange}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Create new VPC" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="create-new">Create new VPC</SelectItem>
                  {awsResources?.vpcs?.map((vpc: any) => (
                    <SelectItem key={vpc.id} value={vpc.id}>
                      {vpc.name} ({vpc.cidrBlock}){vpc.isDefault ? ' - Default' : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <p className="text-xs text-gray-500 mt-1">
              {isReadOnly 
                ? 'This is the VPC your deployment is currently using'
                : 'Optional: Select an existing VPC or leave empty to create a new one'
              }
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">
              {isReadOnly ? 'Assigned Subnets' : 'Existing Subnets'}
            </label>
            {isReadOnly ? (
              <div className="w-full px-3 py-2 border border-border rounded-lg">
                {loadingResources ? (
                  <div className="flex items-center space-x-2">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                    <span className="text-sm text-gray-600">Loading subnet details...</span>
                  </div>
                ) : deployedResources?.subnets && deployedResources.subnets.length > 0 ? (
                  <div className="space-y-2">
                    {deployedResources.subnets.map((subnet: any) => (
                      <div key={subnet.id} className="flex items-center space-x-2">
                        <div>
                          <span className="text-sm font-medium text-foreground">{subnet.name}</span>
                          <span className="text-xs text-gray-500 block">{subnet.id} - {subnet.availabilityZone} ({subnet.cidrBlock})</span>
                        </div>
                      </div>
                    ))}
                    <p className="text-xs text-gray-600 mt-1">
                      {deployedResources.subnets.length} subnet(s) assigned
                    </p>
                  </div>
                ) : (
                  <div className="flex items-center space-x-2">
                    <svg className="h-4 w-4 text-amber-500" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                    <span className="text-sm text-gray-600">Subnet details not available</span>
                  </div>
                )}
              </div>
            ) : !formData.existingVpcId ? (
              <div className="w-full px-3 py-2 border border-border rounded-lg text-gray-500">
                Select a VPC first to see available subnets
              </div>
            ) : availableSubnets.length === 0 ? (
              <div className="w-full px-3 py-2 border border-border rounded-lg text-gray-500">
                No subnets found for selected VPC
              </div>
            ) : (
              <div className="space-y-2 max-h-40 overflow-y-auto border border-gray-300 rounded-lg p-2">
                {availableSubnets.map((subnet: any) => (
                  <label key={subnet.id} className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      checked={selectedSubnets.includes(subnet.id)}
                      onChange={() => handleSubnetToggle(subnet.id)}
                      className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-sm">
                      {subnet.name} ({subnet.cidrBlock}) - {subnet.availabilityZone}
                      {subnet.isPublic ? ' - Public' : ' - Private'}
                    </span>
                  </label>
                ))}
              </div>
            )}
            <p className="text-xs text-gray-500 mt-1">
              {isReadOnly 
                ? 'These are the subnets your deployment is currently using'
                : 'Optional: Select subnets in different availability zones for high availability'
              }
            </p>
            {!isReadOnly && selectedSubnets.length > 0 && (
              <p className="text-xs text-blue-600 mt-1">
                {selectedSubnets.length} subnet(s) selected
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">
              {isReadOnly ? 'Assigned ECS Cluster' : 'Existing ECS Cluster'}
            </label>
            {isReadOnly ? (
              <div className="w-full px-3 py-2 border border-border rounded-lg">
                {loadingResources ? (
                  <div className="flex items-center space-x-2">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                    <span className="text-sm text-gray-600">Loading cluster details...</span>
                  </div>
                ) : deployedResources?.cluster ? (
                  <div className="flex items-center space-x-2">
                    <div>
                      <span className="text-sm font-medium text-foreground block">{deployedResources.cluster.name}</span>
                      <span className="text-xs text-gray-500">{deployedResources.cluster.arn}</span>
                      <span className="text-xs text-blue-600 block">{deployedResources.cluster.runningTasksCount} tasks, {deployedResources.cluster.activeServicesCount} services</span>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center space-x-2">
                    <svg className="h-4 w-4 text-amber-500" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                    <span className="text-sm text-gray-600">Cluster details not available</span>
                  </div>
                )}
              </div>
            ) : loadingResources ? (
              <div className="w-full px-3 py-2 border border-gray-300 rounded-lg text-gray-500">
                Loading ECS clusters...
              </div>
            ) : (
              <Select 
                value={formData.existingClusterArn || "create-new"} 
                onValueChange={(value) => {
                  const actualValue = value === "create-new" ? "" : value
                  setFormData({ ...formData, existingClusterArn: actualValue })
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Create new ECS cluster" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="create-new">Create new ECS cluster</SelectItem>
                  {awsResources?.clusters?.map((cluster: any) => (
                    <SelectItem key={cluster.arn} value={cluster.arn}>
                      {cluster.name} ({cluster.runningTasksCount} running, {cluster.activeServicesCount} services)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            <p className="text-xs text-gray-500 mt-1">
              {isReadOnly 
                ? 'This is the ECS cluster your deployment is currently using'
                : 'Optional: Select an existing ECS cluster or leave empty to create a new one'
              }
            </p>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          {success && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-3">
              <p className="text-sm text-green-600">{success}</p>
            </div>
          )}

          {!isReadOnly && (
            <div className="flex space-x-3 pt-4">
              <Button
                size="sm"
                type="submit"
                disabled={loading}
              >
                {loading ? 'Saving...' : 'Save Configuration'}
              </Button>
              <Button
                size="sm"
                type="button"
                onClick={handleClear}
                disabled={loading}
                variant="outline"
              >
                Clear All
              </Button>
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  )
}