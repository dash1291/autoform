'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useJwtStore } from '@/lib/auth-client'
import { apiClient } from '@/lib/api'

export default function NewProject() {
  const { jwtToken } = useJwtStore()
  const router = useRouter()
  const [formData, setFormData] = useState({
    name: '',
    gitRepoUrl: '',
    branch: 'main',
    cpu: 256,
    memory: 512,
    diskSize: 21,
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [validating, setValidating] = useState(false)
  const [repoInfo, setRepoInfo] = useState<any>(null)

  const validateRepository = async (url: string) => {
    if (!url || !url.includes('github.com')) return

    console.log('Starting repository validation for:', url)
    console.log('Session status:', session ? 'authenticated' : 'not authenticated')
    console.log('User ID:', session?.user?.id)
    
    setValidating(true)
    setError('')
    setRepoInfo(null)

    try {
      console.log('Making fetch request to validate repository')
      const data = await apiClient.validateRepository(url)
      console.log('Response data:', data)

      if (data.valid) {
        setRepoInfo(data.repository)
        // Auto-fill project name and branch if empty
        if (!formData.name && data.repository.name) {
          setFormData(prev => ({ 
            ...prev, 
            name: data.repository.name,
            branch: data.repository.defaultBranch 
          }))
        } else if (data.repository.defaultBranch) {
          setFormData(prev => ({ 
            ...prev, 
            branch: data.repository.defaultBranch 
          }))
        }
      } else {
        setError(data.error)
        
        // If re-authentication is needed, show special message
        if (data.needsReauth) {
          setError(data.error + ' Click here to refresh your GitHub connection.')
        }
        
        // Log debug info for troubleshooting
        if (data.debug) {
          console.error('Repository validation failed:', data.debug)
        }
      }
    } catch (err) {
      setError('Failed to validate repository')
    } finally {
      setValidating(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!jwtToken) return

    setLoading(true)
    setError('')

    try {
      // Validate repository first if not already validated
      if (!repoInfo) {
        await validateRepository(formData.gitRepoUrl)
        if (!repoInfo) {
          setLoading(false)
          return
        }
      }

      await apiClient.createProject(formData)
      router.push('/dashboard')
    } catch (err: any) {
      setError(err.message || 'Failed to create project')
    } finally {
      setLoading(false)
    }
  }

  if (!jwtToken) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Please sign in</h1>
          <p className="text-gray-600">You need to be signed in to create a project.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Create New Project</h1>
          <p className="text-gray-600">Deploy your application to AWS ECS</p>
        </div>

        <div className="bg-white shadow rounded-lg p-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
                Project Name
              </label>
              <input
                type="text"
                id="name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"
                placeholder="my-awesome-app"
                required
              />
              <p className="text-sm text-gray-500 mt-1">
                This will be used as the container name and resource prefix
              </p>
            </div>

            <div>
              <label htmlFor="gitRepoUrl" className="block text-sm font-medium text-gray-700 mb-2">
                Git Repository URL
              </label>
              <div className="relative">
                <input
                  type="url"
                  id="gitRepoUrl"
                  value={formData.gitRepoUrl}
                  onChange={(e) => {
                    setFormData({ ...formData, gitRepoUrl: e.target.value })
                    setRepoInfo(null) // Clear previous validation
                  }}
                  onBlur={(e) => validateRepository(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"
                  placeholder="https://github.com/username/repository"
                  required
                />
                {validating && (
                  <div className="absolute right-3 top-3">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                  </div>
                )}
              </div>
              
              {repoInfo && (
                <div className="mt-2 p-3 bg-green-50 border border-green-200 rounded-lg">
                  <div className="flex items-center">
                    <span className="text-green-600 text-sm font-medium">✅ Repository validated</span>
                    {repoInfo.private && (
                      <span className="ml-2 px-2 py-1 bg-yellow-100 text-yellow-800 text-xs rounded">Private</span>
                    )}
                  </div>
                  <p className="text-sm text-gray-600 mt-1">
                    <strong>{repoInfo.fullName}</strong>
                    {repoInfo.description && ` - ${repoInfo.description}`}
                  </p>
                </div>
              )}
              
              <div className="flex items-center justify-between mt-1">
                <p className="text-sm text-gray-500">
                  Can be public or private repository. Private repos use your GitHub authentication.
                </p>
                {formData.gitRepoUrl && !repoInfo && (
                  <button
                    type="button"
                    onClick={() => validateRepository(formData.gitRepoUrl)}
                    disabled={validating}
                    className="text-sm text-blue-600 hover:text-blue-700 disabled:opacity-50"
                  >
                    {validating ? 'Validating...' : 'Test Access'}
                  </button>
                )}
              </div>
            </div>

            {repoInfo && repoInfo.branches && (
              <div>
                <label htmlFor="branch" className="block text-sm font-medium text-gray-700 mb-2">
                  Branch to Deploy
                </label>
                <select
                  id="branch"
                  value={formData.branch}
                  onChange={(e) => setFormData({ ...formData, branch: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"
                  required
                >
                  {repoInfo.branches.map((branch: string) => (
                    <option key={branch} value={branch}>
                      {branch} {branch === repoInfo.defaultBranch ? '(default)' : ''}
                    </option>
                  ))}
                </select>
                <p className="text-sm text-gray-500 mt-1">
                  Select which branch to deploy from this repository
                </p>
              </div>
            )}

            {/* Resource Configuration Section */}
            <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Resource Configuration</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label htmlFor="cpu" className="block text-sm font-medium text-gray-700 mb-2">
                    CPU (units)
                  </label>
                  <select
                    id="cpu"
                    value={formData.cpu}
                    onChange={(e) => setFormData({ ...formData, cpu: parseInt(e.target.value) })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"
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
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"
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
                    min="21"
                    max="200"
                    value={formData.diskSize}
                    onChange={(e) => setFormData({ ...formData, diskSize: parseInt(e.target.value) || 21 })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"
                  />
                  <p className="text-xs text-gray-500 mt-1">Ephemeral storage (21-200 GB)</p>
                </div>
              </div>
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <p className="text-red-800">{error}</p>
              </div>
            )}

            <div className="flex space-x-4">
              <Button
                type="submit"
                disabled={loading}
                className="flex-1"
              >
                {loading ? 'Creating...' : 'Create Project'}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => router.push('/dashboard')}
              >
                Cancel
              </Button>
            </div>
          </form>
        </div>

        <div className="mt-8 bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h3 className="font-medium text-blue-900 mb-2">What happens next?</h3>
          <ul className="text-sm text-blue-800 space-y-1">
            <li>• Your repository will be cloned</li>
            <li>• A Docker image will be built</li>
            <li>• AWS infrastructure will be provisioned</li>
            <li>• Your application will be deployed to ECS</li>
          </ul>
        </div>
      </div>
    </div>
  )
}