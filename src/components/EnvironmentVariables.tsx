'use client'

import { useState, useEffect } from 'react'
import { EnvironmentVariable } from '@/types'

interface EnvironmentVariablesProps {
  projectId: string
}

export default function EnvironmentVariables({ projectId }: EnvironmentVariablesProps) {
  const [envVars, setEnvVars] = useState<EnvironmentVariable[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isAdding, setIsAdding] = useState(false)
  const [newVar, setNewVar] = useState({
    key: '',
    value: '',
    isSecret: false
  })

  useEffect(() => {
    fetchEnvironmentVariables()
  }, [projectId])

  const fetchEnvironmentVariables = async () => {
    setLoading(true)
    setError(null)
    
    try {
      const response = await fetch(`/api/projects/${projectId}/environment`)
      
      if (!response.ok) {
        throw new Error('Failed to fetch environment variables')
      }
      
      const data = await response.json()
      setEnvVars(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch environment variables')
    } finally {
      setLoading(false)
    }
  }

  const handleAddVariable = async () => {
    if (!newVar.key.trim()) {
      setError('Variable name is required')
      return
    }

    if (!newVar.isSecret && !newVar.value.trim()) {
      setError('Value is required for non-secret variables')
      return
    }

    if (newVar.isSecret && !newVar.value.trim()) {
      setError('Value is required for secrets')
      return
    }

    try {
      const response = await fetch(`/api/projects/${projectId}/environment`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newVar),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.error || 'Failed to add environment variable')
      }

      await fetchEnvironmentVariables()
      setNewVar({ key: '', value: '', isSecret: false })
      setIsAdding(false)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add environment variable')
    }
  }

  const handleDeleteVariable = async (key: string) => {
    if (!confirm(`Are you sure you want to delete the variable "${key}"?`)) {
      return
    }

    try {
      const response = await fetch(`/api/projects/${projectId}/environment?key=${encodeURIComponent(key)}`, {
        method: 'DELETE',
      })

      if (!response.ok) {
        throw new Error('Failed to delete environment variable')
      }

      await fetchEnvironmentVariables()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete environment variable')
    }
  }

  const validateKey = (key: string) => {
    // Environment variable names should be valid identifiers
    const regex = /^[A-Za-z_][A-Za-z0-9_]*$/
    return regex.test(key)
  }

  return (
    <div className="space-y-6">
      {/* Header with Add Button */}
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-lg font-medium text-gray-900">Environment Variables</h3>
          <p className="text-sm text-gray-500">
            Configure environment variables and secrets for your application. Secrets are stored securely in AWS Secrets Manager.
          </p>
        </div>
        <button
          onClick={() => setIsAdding(true)}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
        >
          Add Variable
        </button>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Add Variable Form */}
      {isAdding && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
          <h4 className="text-md font-medium text-gray-900 mb-4">Add Environment Variable</h4>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Variable Name
              </label>
              <input
                type="text"
                value={newVar.key}
                onChange={(e) => setNewVar({ ...newVar, key: e.target.value.toUpperCase() })}
                placeholder="API_KEY"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {newVar.key && !validateKey(newVar.key) && (
                <p className="text-xs text-red-600 mt-1">
                  Variable name should contain only letters, numbers, and underscores, starting with a letter or underscore
                </p>
              )}
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Value
              </label>
              <input
                type={newVar.isSecret ? "password" : "text"}
                value={newVar.value}
                onChange={(e) => setNewVar({ ...newVar, value: e.target.value })}
                placeholder={newVar.isSecret ? "Enter secret value" : "Enter value"}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <div className="mt-4 flex items-center">
            <input
              type="checkbox"
              id="isSecret"
              checked={newVar.isSecret}
              onChange={(e) => setNewVar({ ...newVar, isSecret: e.target.checked })}
              className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
            />
            <label htmlFor="isSecret" className="ml-2 block text-sm text-gray-700">
              This is a secret (will be stored in AWS Secrets Manager)
            </label>
          </div>

          <div className="mt-4 flex gap-2">
            <button
              onClick={handleAddVariable}
              disabled={!newVar.key || !validateKey(newVar.key) || !newVar.value}
              className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Add Variable
            </button>
            <button
              onClick={() => {
                setIsAdding(false)
                setNewVar({ key: '', value: '', isSecret: false })
                setError(null)
              }}
              className="bg-gray-300 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-400 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Variables List */}
      {loading ? (
        <div className="text-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
          <p className="text-gray-500 mt-2">Loading environment variables...</p>
        </div>
      ) : envVars.length === 0 ? (
        <div className="text-center py-8 bg-gray-50 rounded-lg">
          <p className="text-gray-500">No environment variables configured.</p>
          <p className="text-sm text-gray-400 mt-1">
            Add environment variables to configure your application.
          </p>
        </div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Variable Name
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Type
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Value
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {envVars.map((envVar) => (
                <tr key={envVar.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <code className="text-sm font-mono bg-gray-100 px-2 py-1 rounded">
                      {envVar.key}
                    </code>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                      envVar.isSecret 
                        ? 'bg-red-100 text-red-800' 
                        : 'bg-green-100 text-green-800'
                    }`}>
                      {envVar.isSecret ? 'Secret' : 'Environment Variable'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {envVar.isSecret ? (
                      <span className="text-gray-400">••••••••</span>
                    ) : (
                      <code className="bg-gray-100 px-2 py-1 rounded text-xs">
                        {envVar.value || '(empty)'}
                      </code>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    <button
                      onClick={() => handleDeleteVariable(envVar.key)}
                      className="text-red-600 hover:text-red-900 transition-colors"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {envVars.length > 0 && (
        <div className="text-xs text-gray-500 bg-blue-50 p-3 rounded-lg">
          <p className="font-medium text-blue-900 mb-1">ℹ️ Important Notes:</p>
          <ul className="list-disc list-inside space-y-1 text-blue-800">
            <li>Environment variables will be available to your application after the next deployment</li>
            <li>Secrets are stored securely in AWS Secrets Manager and are not visible in the UI</li>
            <li>Variable names are automatically converted to uppercase</li>
            <li>Changes require a new deployment to take effect</li>
          </ul>
        </div>
      )}
    </div>
  )
}