'use client'

import { useState } from 'react'
import { Project } from '@/types'

interface ResourceConfigurationProps {
  projectId: string
  project: Project
  onUpdate: () => void
}

export default function ResourceConfiguration({ projectId, project, onUpdate }: ResourceConfigurationProps) {
  const [formData, setFormData] = useState({
    cpu: project.cpu || 256,
    memory: project.memory || 512,
    diskSize: project.diskSize || 20,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setSuccess('')

    try {
      const response = await fetch(`/api/projects/${projectId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      })

      if (response.ok) {
        setSuccess('Resource configuration updated successfully!')
        onUpdate()
      } else {
        const data = await response.json()
        setError(data.error || 'Failed to update resource configuration')
      }
    } catch (err) {
      setError('Failed to update resource configuration')
    } finally {
      setLoading(false)
    }
  }

  // Check if form data has changed from original values
  const hasChanges = 
    formData.cpu !== (project.cpu || 256) ||
    formData.memory !== (project.memory || 512) ||
    formData.diskSize !== (project.diskSize || 20)

  const isDeploying = project.status === 'DEPLOYING' || project.status === 'BUILDING' || project.status === 'CLONING'

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-gray-900">Resource Configuration</h2>
      </div>
      
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label htmlFor="cpu" className="block text-sm font-medium text-gray-700 mb-2">
              CPU (units)
            </label>
            <select
              id="cpu"
              value={formData.cpu}
              onChange={(e) => setFormData({ ...formData, cpu: parseInt(e.target.value) })}
              disabled={isDeploying}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option value={256}>256 (0.25 vCPU)</option>
              <option value={512}>512 (0.5 vCPU)</option>
              <option value={1024}>1024 (1 vCPU)</option>
              <option value={2048}>2048 (2 vCPU)</option>
              <option value={4096}>4096 (4 vCPU)</option>
            </select>
            <p className="text-xs text-gray-500 mt-1">AWS Fargate CPU allocation</p>
          </div>

          <div>
            <label htmlFor="memory" className="block text-sm font-medium text-gray-700 mb-2">
              Memory (MB)
            </label>
            <select
              id="memory"
              value={formData.memory}
              onChange={(e) => setFormData({ ...formData, memory: parseInt(e.target.value) })}
              disabled={isDeploying}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option value={512}>512 MB</option>
              <option value={1024}>1 GB</option>
              <option value={2048}>2 GB</option>
              <option value={4096}>4 GB</option>
              <option value={8192}>8 GB</option>
              <option value={16384}>16 GB</option>
              <option value={30720}>30 GB</option>
            </select>
            <p className="text-xs text-gray-500 mt-1">Container memory limit</p>
          </div>

          <div>
            <label htmlFor="diskSize" className="block text-sm font-medium text-gray-700 mb-2">
              Disk Size (GB)
            </label>
            <input
              type="number"
              id="diskSize"
              min="20"
              max="200"
              value={formData.diskSize}
              onChange={(e) => setFormData({ ...formData, diskSize: parseInt(e.target.value) || 20 })}
              disabled={isDeploying}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <p className="text-xs text-gray-500 mt-1">Ephemeral storage (20-200 GB)</p>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-800">{error}</p>
          </div>
        )}

        {success && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4">
            <p className="text-green-800">{success}</p>
          </div>
        )}

        {isDeploying && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <p className="text-yellow-800">
              Cannot modify resource configuration while deployment is in progress.
            </p>
          </div>
        )}

        <div className="flex space-x-4">
          <button
            type="submit"
            disabled={loading || isDeploying || !hasChanges}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </form>
    </div>
  )
}