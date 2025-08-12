'use client'

import { useState, useEffect } from 'react'
import { EnvironmentVariable } from '@/types'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiClient } from '@/lib/api'

interface EnvironmentVariablesProps {
  environmentId: string
}

interface EnvVarState {
  key: string;
  value: string;
  isSecret: boolean;
}

interface EnvVarDisplay extends Omit<EnvironmentVariable, 'isSecret'> {
  isSecret: boolean;
}

type EnvVarResponse = Omit<EnvironmentVariable, 'createdAt' | 'updatedAt'> & {
  createdAt: string;
  updatedAt: string;
};

export default function EnvironmentVariables({ environmentId }: EnvironmentVariablesProps) {
  const [envVars, setEnvVars] = useState<EnvironmentVariable[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isAdding, setIsAdding] = useState(false)
  const [editingVar, setEditingVar] = useState<string | null>(null)
  const [newVar, setNewVar] = useState<EnvVarState>({
    key: '',
    value: '',
    isSecret: false
  })
  const [editVar, setEditVar] = useState<EnvVarState>({
    key: '',
    value: '',
    isSecret: false
  })
  const [importedVars, setImportedVars] = useState<EnvVarState[]>([])
  const [showImportModal, setShowImportModal] = useState(false)
  const [envFileContent, setEnvFileContent] = useState('')
  const [showPreview, setShowPreview] = useState(false)

  useEffect(() => {
    fetchEnvironmentVariables()
  }, [environmentId])

  const isEnvironmentVariable = (envVar: any): envVar is EnvironmentVariable => {
    return (
      typeof envVar === 'object' &&
      typeof envVar.id === 'string' &&
      typeof envVar.environmentId === 'string' &&
      typeof envVar.projectId === 'string' &&
      typeof envVar.key === 'string' &&
      (typeof envVar.value === 'string' || envVar.value === undefined) &&
      typeof envVar.isSecret === 'boolean' &&
      (typeof envVar.secretKey === 'string' || envVar.secretKey === undefined) &&
      envVar.createdAt instanceof Date &&
      envVar.updatedAt instanceof Date
    );
  };

  const fetchEnvironmentVariables = async () => {
    setLoading(true)
    setError(null)
    
    try {
      const data = await apiClient.getEnvironmentVariables(environmentId)
      
      // Transform the API response
      const transformedVars = data.map((envVar) => ({
        ...envVar,
        createdAt: new Date(envVar.createdAt),
        updatedAt: new Date(envVar.updatedAt)
      }));
      setEnvVars(transformedVars)
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

    if (!Boolean(newVar.isSecret) && !newVar.value.trim()) {
      setError('Value is required for non-secret variables')
      return
    }

    if (Boolean(newVar.isSecret) && !newVar.value.trim()) {
      setError('Value is required for secrets')
      return
    }

    try {
      await apiClient.createEnvironmentVariable(environmentId, newVar)
      
      await fetchEnvironmentVariables()
      setNewVar({ key: '', value: '', isSecret: false })
      setIsAdding(false)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add environment variable')
    }
  }

  const handleEditVariable = (envVar: EnvironmentVariable) => {
    setEditingVar(envVar.key)
    setEditVar({
      key: envVar.key,
      value: envVar.isSecret ? '' : (envVar.value || ''),
      isSecret: envVar.isSecret
    })
    setError(null)
  }

  const handleUpdateVariable = async () => {
    if (!editVar.key.trim()) {
      setError('Variable name is required')
      return
    }

    if (!Boolean(editVar.isSecret) && !editVar.value.trim()) {
      setError('Value is required for non-secret variables')
      return
    }

    if (Boolean(editVar.isSecret) && !editVar.value.trim()) {
      setError('Value is required for secrets')
      return
    }

    try {
      // Find the env var ID for updating
      const envVar = envVars.find(v => v.key === editVar.key)
      if (!envVar) {
        throw new Error('Environment variable not found')
      }
      
      await apiClient.updateEnvironmentVariable(environmentId, envVar.id, editVar)
      
      await fetchEnvironmentVariables()
      setEditingVar(null)
      setEditVar({ key: '', value: '', isSecret: false })
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update environment variable')
    }
  }

  const handleCancelEdit = () => {
    setEditingVar(null)
    setEditVar({ key: '', value: '', isSecret: false })
    setError(null)
  }

  const handleDeleteVariable = async (key: string) => {
    if (!confirm(`Are you sure you want to delete the variable "${key}"?`)) {
      return
    }

    try {
      // Find the env var ID for deleting
      const envVar = envVars.find(v => v.key === key)
      if (!envVar) {
        throw new Error('Environment variable not found')
      }
      
      await apiClient.deleteEnvironmentVariable(environmentId, envVar.id)
      
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

  const parseEnvFile = (content: string): EnvVarState[] => {
    const lines = content.split('\n')
    const vars: EnvVarState[] = []
    
    for (const line of lines) {
      // Skip empty lines and comments
      const trimmedLine = line.trim()
      if (!trimmedLine || trimmedLine.startsWith('#')) {
        continue
      }
      
      // Parse KEY=VALUE format
      const equalIndex = trimmedLine.indexOf('=')
      if (equalIndex > 0) {
        const key = trimmedLine.substring(0, equalIndex).trim()
        let value = trimmedLine.substring(equalIndex + 1).trim()
        
        // Remove surrounding quotes if present
        if ((value.startsWith('"') && value.endsWith('"')) || 
            (value.startsWith("'") && value.endsWith("'"))) {
          value = value.slice(1, -1)
        }
        
        // Only add valid keys
        if (validateKey(key)) {
          vars.push({
            key,
            value,
            isSecret: false
          })
        }
      }
    }
    
    return vars
  }

  const handleParseEnvContent = () => {
    if (!envFileContent.trim()) {
      setError('Please paste your .env file content')
      return
    }
    
    const parsed = parseEnvFile(envFileContent)
    
    if (parsed.length === 0) {
      setError('No valid environment variables found in the content')
      return
    }
    
    // Filter out variables that already exist
    const existingKeys = new Set(envVars.map(v => v.key))
    const newVarsToImport = parsed.filter(v => !existingKeys.has(v.key))
    
    if (newVarsToImport.length === 0) {
      setError('All variables in the content already exist')
      return
    }
    
    setImportedVars(newVarsToImport)
    setShowPreview(true)
    setError(null)
  }

  const handleImportConfirm = async () => {
    setLoading(true)
    setError(null)
    
    try {
      // Import all variables
      for (const varToImport of importedVars) {
        await apiClient.createEnvironmentVariable(environmentId, varToImport)
      }
      
      await fetchEnvironmentVariables()
      setShowImportModal(false)
      setShowPreview(false)
      setImportedVars([])
      setEnvFileContent('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import environment variables')
    } finally {
      setLoading(false)
    }
  }

  const handleImportCancel = () => {
    setShowImportModal(false)
    setShowPreview(false)
    setImportedVars([])
    setEnvFileContent('')
    setError(null)
  }

  return (
    <div className="space-y-6">
      {/* Header with Add and Import Buttons */}
      <div className="flex gap-2">
        <Button size="sm" onClick={() => setIsAdding(true)}>
          Add Variable
        </Button>
        <Button 
          size="sm" 
          variant="outline"
          onClick={() => setShowImportModal(true)}
        >
          Import from .env
        </Button>
      </div>
      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Add Variable Form */}
      {isAdding && (
        <div className="border border-gray-700 rounded-lg p-4">
          <h4 className="text-sm mb-4">Add Environment Variable</h4>
          
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
                className="w-full bg-background border border-gray-700 text-sm rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                type={Boolean(newVar.isSecret) ? "password" : "text"}
                value={newVar.value}
                onChange={(e) => setNewVar({ ...newVar, value: e.target.value })}
                placeholder={Boolean(newVar.isSecret) ? "Enter secret value" : "Enter value"}
                className="w-full bg-background border text-sm border-gray-700 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <div className="mt-4 flex items-center">
            <input
              type="checkbox"
              id="isSecret"
              checked={Boolean(newVar.isSecret)}
              onChange={(e) => setNewVar({ ...newVar, isSecret: Boolean(e.target.checked) })}
              className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-700 rounded"
            />
            <label htmlFor="isSecret" className="ml-2 block text-sm text-gray-700">
              This is a secret (will be stored in AWS Secrets Manager)
            </label>
          </div>

          <div className="mt-4 flex gap-2">
            <Button
              onClick={handleAddVariable}
              disabled={!newVar.key || !validateKey(newVar.key) || !newVar.value}
            >
              Save
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setIsAdding(false)
                setNewVar({ key: '', value: '', isSecret: false })
                setError(null)
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Variables List */}
      {loading ? (
        <div className="text-center py-8">
          <Spinner className="mx-auto" />
          <p className="text-gray-500 mt-2">Loading environment variables...</p>
        </div>
      ) : envVars.length === 0 ? (
        <div className="text-center py-8 rounded-lg">
          <p className="text-gray-500">No environment variables configured.</p>
          <p className="text-sm text-gray-400 mt-1">
            Add environment variables to configure your application.
          </p>
        </div>
      ) : (
        <div className="border border-gray-700 rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[800px] table-fixed divide-y divide-gray-700">
            <thead>
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-48">
                  Variable Name
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-32">
                  Type
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-64">
                  Value
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-32">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {envVars.map((envVar) => (
                <tr key={envVar.id}>
                  {editingVar === envVar.key ? (
                    // Edit mode
                    <>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <input
                          type="text"
                          value={editVar.key}
                          onChange={(e) => setEditVar({ ...editVar, key: e.target.value.toUpperCase() })}
                          disabled
                          className="text-sm font-mono px-2 py-1 rounded border bg-primary border-gray-700 w-full cursor-not-allowed"
                        />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          <input
                            type="checkbox"
                            checked={Boolean(editVar.isSecret)}
                            onChange={(e) => setEditVar({ ...editVar, isSecret: e.target.checked })}
                            className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-700 rounded mr-2"
                          />
                          <span className="text-xs">Secret</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 w-48">
                        <input
                          type={Boolean(editVar.isSecret) ? "password" : "text"}
                          value={editVar.value}
                          onChange={(e) => setEditVar({ ...editVar, value: e.target.value })}
                          placeholder={Boolean(editVar.isSecret) ? "Enter new secret value" : "Enter value"}
                          className="text-sm bg-background px-2 py-1 rounded border border-gray-700 w-full focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            onClick={handleUpdateVariable}
                            disabled={!editVar.value || (Boolean(editVar.key) && !validateKey(editVar.key))}
                          >
                            Save
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={handleCancelEdit}
                          >
                            Cancel
                          </Button>
                        </div>
                      </td>
                    </>
                  ) : (
                    // View mode
                    <>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <code className="text-sm font-mono px-2 py-1 rounded">
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
                      <td className="px-6 py-4 w-48 text-sm text-gray-500">
                        {envVar.isSecret ? (
                          <span className="text-gray-400">••••••••</span>
                        ) : (
                          <div className="truncate">
                            <code className="bg-background px-2 py-1 rounded text-xs">
                              {envVar.value || '(empty)'}
                            </code>
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleEditVariable(envVar)}
                          >
                            Edit
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleDeleteVariable(envVar.key)}
                            className="text-destructive hover:text-destructive"
                          >
                            Delete
                          </Button>
                        </div>
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}

      {/* Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-background border border-gray-700 rounded-lg p-6 max-w-3xl w-full max-h-[80vh] overflow-y-auto">
            <h3 className="text-lg font-semibold mb-4">Import Environment Variables</h3>
            
            {!showPreview ? (
              <>
                <p className="text-sm text-gray-500 mb-4">
                  Paste your .env file content below. Lines should be in KEY=VALUE format.
                </p>
                
                <textarea
                  value={envFileContent}
                  onChange={(e) => setEnvFileContent(e.target.value)}
                  className="w-full h-64 bg-background border border-gray-700 rounded-lg p-3 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                
                <div className="flex justify-end gap-2 mt-4">
                  <Button
                    variant="outline"
                    onClick={handleImportCancel}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleParseEnvContent}
                    disabled={!envFileContent.trim()}
                  >
                    Preview Import
                  </Button>
                </div>
              </>
            ) : (
              <>
                <p className="text-sm text-muted-foreground mb-4">
                  The following {importedVars.length} variable(s) will be imported:
                </p>
                
                <div className="border border-gray-700 rounded-lg overflow-hidden mb-4">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-gray-700">
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Variable Name</th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Value</th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                      </tr>
                    </thead>
                    <tbody>
                      {importedVars.map((v, index) => (
                        <tr key={index} className="border-b border-gray-700">
                          <td className="px-4 py-2">
                            <code className="text-sm font-mono">{v.key}</code>
                          </td>
                          <td className="px-4 py-2">
                            <code className="text-xs bg-background px-2 py-1 rounded truncate block max-w-xs">
                              {v.value.length > 50 ? v.value.substring(0, 50) + '...' : v.value}
                            </code>
                          </td>
                          <td className="px-4 py-2">
                            <div className="flex items-center">
                              <input
                                type="checkbox"
                                checked={v.isSecret}
                                onChange={(e) => {
                                  const updated = [...importedVars]
                                  updated[index].isSecret = e.target.checked
                                  setImportedVars(updated)
                                }}
                                className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-700 rounded mr-2"
                              />
                              <span className="text-xs">Secret</span>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                
                <div className="flex justify-end gap-2">
                  <Button
                    variant="outline"
                    onClick={() => {
                      setShowPreview(false)
                      setImportedVars([])
                    }}
                    disabled={loading}
                  >
                    Back
                  </Button>
                  <Button
                    onClick={handleImportConfirm}
                    disabled={loading}
                  >
                    {loading ? 'Importing...' : 'Import All'}
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}