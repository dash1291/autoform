'use client'

import { useState, useEffect } from 'react'

interface NetworkConfigurationProps {
  projectId: string
  project: any
  onUpdate: () => void
}

export default function NetworkConfiguration({ projectId, project, onUpdate }: NetworkConfigurationProps) {
  const isDeployed = project?.status === 'DEPLOYED' || project?.ecsServiceArn || project?.albArn
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
      const response = await fetch('/api/aws/resources')
      if (response.ok) {
        const data = await response.json()
        setAwsResources(data)
      }
    } catch (err) {
      console.error('Failed to fetch AWS resources:', err)
    } finally {
      setLoadingResources(false)
    }
  }

  const fetchDeployedResources = async () => {
    setLoadingResources(true)
    try {
      const response = await fetch(`/api/projects/${projectId}/deployed-resources`)
      if (response.ok) {
        const data = await response.json()
        setDeployedResources(data)
      }
    } catch (err) {
      console.error('Failed to fetch deployed resources:', err)
    } finally {
      setLoadingResources(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (isReadOnly) {
      setError('Network configuration cannot be changed for deployed projects')
      return
    }
    
    setLoading(true)
    setError('')
    setSuccess('')

    try {
      const payload = {
        existingVpcId: formData.existingVpcId || null,
        existingSubnetIds: selectedSubnets.length > 0 ? selectedSubnets : null,
        existingClusterArn: formData.existingClusterArn || null
      }

      const response = await fetch(`/api/projects/${projectId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      })

      if (response.ok) {
        setSuccess('Network configuration updated successfully!')
        onUpdate()
        setTimeout(() => setSuccess(''), 3000)
      } else {
        const errorData = await response.json()
        setError(errorData.error || 'Failed to update network configuration')
      }
    } catch (err) {
      setError('Failed to update network configuration')
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
    setFormData({ ...formData, existingVpcId: vpcId })
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
    <div className="space-y-6">
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-lg font-medium text-gray-900">Network Configuration</h3>
        </div>
        <div className="text-sm text-gray-600 mb-4">
          Configure existing AWS network resources to use instead of creating new ones. Leave fields empty to create new resources automatically. 
          <button
            type="button"
            onClick={() => setShowTips(!showTips)}
            className="flex items-center space-x-1 text-blue-600 hover:text-blue-700 text-sm font-medium"
          >
            <svg
              className={`w-4 h-4 transition-transform ${showTips ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
            <span>Configuration Tips</span>
          </button>
        </div>
        
        {showTips && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
            <h4 className="font-medium text-blue-900 mb-2">💡 Configuration Tips</h4>
            <ul className="text-sm text-blue-800 space-y-1">
              <li>• VPC and subnets must be in the same AWS region as your project</li>
              <li>• Subnets should be in different availability zones for high availability</li>
              <li>• ECS cluster must exist and be in ACTIVE status</li>
              <li>• These settings only apply to new deployments</li>
              <li>• Leave fields empty to let the system create resources automatically</li>
            </ul>
          </div>
        )}
        
        {isReadOnly && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
            <div className="flex items-start">
              <div className="flex-shrink-0">
                <svg className="h-5 w-5 text-blue-400" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                </svg>
              </div>
              <div className="ml-3">
                <h4 className="text-sm font-medium text-blue-800">Network Configuration Locked</h4>
                <div className="mt-1 text-sm text-blue-700">
                  <p>This project has been deployed and network settings are now read-only. To use different network settings, create a new project.</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {isReadOnly ? 'Assigned VPC' : 'Existing VPC'}
          </label>
          {isReadOnly ? (
            <div className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-50">
              {loadingResources ? (
                <div className="flex items-center space-x-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                  <span className="text-sm text-gray-600">Loading VPC details...</span>
                </div>
              ) : deployedResources?.vpc ? (
                <div className="flex items-center space-x-2">
                  <div>
                    <span className="text-sm font-medium text-gray-900">{deployedResources.vpc.name}</span>
                    <span className="text-xs text-gray-500 block">{deployedResources.vpc.id} ({deployedResources.vpc.cidrBlock})</span>
                  </div>
                  {formData.existingVpcId && (
                    <span className="text-xs text-green-600">(Pre-existing)</span>
                  )}
                </div>
              ) : (
                <div className="flex items-center space-x-2">
                  <svg className="h-4 w-4 text-amber-500" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                  <span className="text-sm text-gray-600">VPC details not available</span>
                </div>
              )}
            </div>
          ) : loadingResources ? (
            <div className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500">
              Loading VPCs...
            </div>
          ) : (
            <select
              id="existingVpcId"
              value={formData.existingVpcId}
              onChange={(e) => handleVpcChange(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">Create new VPC</option>
              {awsResources?.vpcs?.map((vpc: any) => (
                <option key={vpc.id} value={vpc.id}>
                  {vpc.name} ({vpc.cidrBlock}){vpc.isDefault ? ' - Default' : ''}
                </option>
              ))}
            </select>
          )}
          <p className="text-xs text-gray-500 mt-1">
            {isReadOnly 
              ? 'This is the VPC your deployment is currently using'
              : 'Optional: Select an existing VPC or leave empty to create a new one'
            }
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {isReadOnly ? 'Assigned Subnets' : 'Existing Subnets'}
          </label>
          {isReadOnly ? (
            <div className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-50">
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
                        <span className="text-sm font-medium text-gray-900">{subnet.name}</span>
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
            <div className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500">
              Select a VPC first to see available subnets
            </div>
          ) : availableSubnets.length === 0 ? (
            <div className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500">
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
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {isReadOnly ? 'Assigned ECS Cluster' : 'Existing ECS Cluster'}
          </label>
          {isReadOnly ? (
            <div className="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-50">
              {loadingResources ? (
                <div className="flex items-center space-x-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                  <span className="text-sm text-gray-600">Loading cluster details...</span>
                </div>
              ) : deployedResources?.cluster ? (
                <div className="flex items-center space-x-2">
                  <div>
                    <span className="text-sm font-medium text-gray-900 block">{deployedResources.cluster.name}</span>
                    <span className="text-xs text-gray-500">{deployedResources.cluster.arn}</span>
                    <span className="text-xs text-blue-600 block">{deployedResources.cluster.runningTasksCount} tasks, {deployedResources.cluster.activeServicesCount} services</span>
                  </div>
                  {formData.existingClusterArn && (
                    <span className="text-xs text-green-600">(Pre-existing)</span>
                  )}
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
            <div className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-gray-500">
              Loading ECS clusters...
            </div>
          ) : (
            <select
              id="existingClusterArn"
              value={formData.existingClusterArn}
              onChange={(e) => setFormData({ ...formData, existingClusterArn: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">Create new ECS cluster</option>
              {awsResources?.clusters?.map((cluster: any) => (
                <option key={cluster.arn} value={cluster.arn}>
                  {cluster.name} ({cluster.runningTasksCount} running, {cluster.activeServicesCount} services)
                </option>
              ))}
            </select>
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
            <button
              type="submit"
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Saving...' : 'Save Configuration'}
            </button>
            <button
              type="button"
              onClick={handleClear}
              disabled={loading}
              className="bg-gray-300 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Clear All
            </button>
          </div>
        )}
      </form>
    </div>
  )
}