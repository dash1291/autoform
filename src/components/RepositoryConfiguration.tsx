'use client'

import { useState } from 'react'
import { Project } from '@/types'

interface RepositoryConfigurationProps {
  projectId: string
  project: Project
  onUpdate: () => void
}

export default function RepositoryConfiguration({ projectId, project, onUpdate }: RepositoryConfigurationProps) {
  const [formData, setFormData] = useState({
    gitRepoUrl: project.gitRepoUrl || '',
    branch: project.branch || 'main',
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
        setSuccess('Repository configuration updated successfully!')
        onUpdate()
      } else {
        const data = await response.json()
        setError(data.error || 'Failed to update repository configuration')
      }
    } catch (err) {
      setError('Failed to update repository configuration')
    } finally {
      setLoading(false)
    }
  }

  // Check if form data has changed from original values
  const hasChanges = 
    formData.gitRepoUrl !== (project.gitRepoUrl || '') ||
    formData.branch !== (project.branch || 'main')

  const isDeploying = project.status === 'DEPLOYING' || project.status === 'BUILDING' || project.status === 'CLONING'

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-gray-900">Repository Configuration</h2>
      </div>
      
      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label htmlFor="gitRepoUrl" className="block text-sm font-medium text-gray-700 mb-2">
            Repository URL
          </label>
          <input
            type="url"
            id="gitRepoUrl"
            value={formData.gitRepoUrl}
            onChange={(e) => setFormData({ ...formData, gitRepoUrl: e.target.value })}
            disabled={isDeploying}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            placeholder="https://github.com/username/repository"
            required
          />
          <p className="text-xs text-gray-500 mt-1">GitHub repository URL for your project</p>
        </div>

        <div>
          <label htmlFor="branch" className="block text-sm font-medium text-gray-700 mb-2">
            Branch
          </label>
          <input
            type="text"
            id="branch"
            value={formData.branch}
            onChange={(e) => setFormData({ ...formData, branch: e.target.value })}
            disabled={isDeploying}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            placeholder="main"
            required
          />
          <p className="text-xs text-gray-500 mt-1">Git branch to deploy from</p>
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
              Cannot modify repository configuration while deployment is in progress.
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

      <div className="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
        <h4 className="font-medium text-yellow-900 mb-2">⚠️ Important</h4>
        <p className="text-sm text-yellow-800">
          Repository changes require a new deployment to take effect. Make sure the new repository URL is accessible with your GitHub authentication.
        </p>
      </div>
    </div>
  )
}