'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import { Project } from '@/types'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { CheckCircle, GitBranch, Loader2, Webhook, Copy, Trash2, ExternalLink, AlertCircle } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface RepositoryConfigurationProps {
  projectId: string
  project: Project
  onUpdate: () => void
}

interface WebhookConfig {
  webhookUrl: string
  webhookSecret: string
  instructions?: Record<string, string>
  automatic?: boolean
  status?: string
  webhookId?: string
}

export default function RepositoryConfiguration({ projectId, project, onUpdate }: RepositoryConfigurationProps) {
  const { data: session } = useSession()
  const [formData, setFormData] = useState({
    gitRepoUrl: project.gitRepoUrl || '',
    branch: project.branch || 'main',
    subdirectory: project.subdirectory || '',
    port: project.port || 3000,
    healthCheckPath: project.healthCheckPath || '/health',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [validating, setValidating] = useState(false)
  const [repoInfo, setRepoInfo] = useState<any>(null)
  const [branches, setBranches] = useState<string[]>([])
  const [validationTimeout, setValidationTimeout] = useState<NodeJS.Timeout | null>(null)
  
  // Webhook state
  const [autoDeployEnabled, setAutoDeployEnabled] = useState(project.autoDeployEnabled || false)
  const [webhookConfig, setWebhookConfig] = useState<WebhookConfig | null>(null)
  const [webhookConfigured, setWebhookConfigured] = useState(project.webhookConfigured || false)
  const [webhookLoading, setWebhookLoading] = useState(false)
  const [showWebhookInstructions, setShowWebhookInstructions] = useState(false)

  const validateRepository = async (url: string) => {
    if (!url || !url.includes('github.com')) return

    setValidating(true)
    setError('')
    setRepoInfo(null)

    try {
      const data = await apiClient.validateRepository(url)

      if (data.valid && data.repository) {
        setRepoInfo(data.repository)
        setBranches(data.repository.branches || [data.repository.defaultBranch])
      } else {
        setBranches([])
        setError(data.error || 'Failed to validate repository')
      }
    } catch (err) {
      setError('Failed to validate repository')
      setBranches([])
    } finally {
      setValidating(false)
    }
  }

  const handleRepoUrlChange = (url: string) => {
    setFormData({ ...formData, gitRepoUrl: url })
    setError('')
    setSuccess('')
    setRepoInfo(null)
    setBranches([])

    if (validationTimeout) {
      clearTimeout(validationTimeout)
    }

    if (url && url.includes('github.com')) {
      const timeout = setTimeout(() => {
        validateRepository(url)
      }, 1000)
      setValidationTimeout(timeout)
    }
  }

  useEffect(() => {
    return () => {
      if (validationTimeout) {
        clearTimeout(validationTimeout)
      }
    }
  }, [validationTimeout])

  // Webhook methods
  const handleAutoDeployToggle = async (enabled: boolean) => {
    setWebhookLoading(true)
    setError('')
    setSuccess('')

    try {
      await apiClient.updateProject(projectId, { autoDeployEnabled: enabled })
      setAutoDeployEnabled(enabled)
      
      if (enabled && !webhookConfig) {
        // Configure webhook when enabling auto-deploy
        await configureWebhook()
      }
      
      setSuccess(enabled ? 'Auto-deploy enabled!' : 'Auto-deploy disabled!')
      onUpdate()
    } catch (err) {
      setError('Failed to update auto-deploy setting')
      setAutoDeployEnabled(!enabled) // Revert toggle
    } finally {
      setWebhookLoading(false)
    }
  }

  const configureWebhook = async () => {
    setWebhookLoading(true)
    setError('')

    try {
      // Pass GitHub access token if available
      const config = await apiClient.configureWebhook(
        projectId, 
        session?.accessToken
      )
      
      setWebhookConfig(config)
      
      if (config.automatic) {
        // Webhook was created automatically
        setWebhookConfigured(true)
        setSuccess(
          config.status === 'created' ? 'Webhook created automatically!' :
          config.status === 'updated' ? 'Webhook updated automatically!' :
          'Webhook already exists!'
        )
        onUpdate()
      } else {
        // Manual setup required
        setShowWebhookInstructions(true)
        setSuccess('Webhook configuration generated! Please follow the instructions to complete setup.')
      }
    } catch (err) {
      setError('Failed to configure webhook')
    } finally {
      setWebhookLoading(false)
    }
  }

  const deleteWebhookConfig = async () => {
    if (!confirm('Are you sure you want to delete the webhook configuration? This will disable auto-deploy.')) {
      return
    }

    setWebhookLoading(true)
    setError('')

    try {
      // Pass GitHub access token to delete from GitHub too
      await apiClient.deleteWebhookConfig(projectId, session?.accessToken)
      setWebhookConfig(null)
      setAutoDeployEnabled(false)
      setWebhookConfigured(false)
      setShowWebhookInstructions(false)
      setSuccess('Webhook configuration deleted!')
      onUpdate()
    } catch (err) {
      setError('Failed to delete webhook configuration')
    } finally {
      setWebhookLoading(false)
    }
  }

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setSuccess('Copied to clipboard!')
      setTimeout(() => setSuccess(''), 2000)
    } catch (err) {
      setError('Failed to copy to clipboard')
    }
  }

  const openGitHubSettings = () => {
    if (formData.gitRepoUrl) {
      const settingsUrl = `${formData.gitRepoUrl}/settings/hooks`
      window.open(settingsUrl, '_blank')
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setSuccess('')

    try {
      const response = await apiClient.updateProject(projectId, formData)
      
      let message = 'Repository configuration updated successfully!'
      
      // Check if health check was updated
      if (response.healthCheckUpdateStatus) {
        if (response.healthCheckUpdateStatus === 'success') {
          message += ' Health check endpoint updated in load balancer.'
        } else if (response.healthCheckUpdateStatus.startsWith('failed:')) {
          message += ` Note: Health check update failed - ${response.healthCheckUpdateStatus.substring(8)}`
        } else if (response.healthCheckUpdateStatus.startsWith('skipped:')) {
          message += ` Health check update skipped - ${response.healthCheckUpdateStatus.substring(9)}`
        }
      }
      
      setSuccess(message)
      onUpdate()
    } catch (err) {
      setError('Failed to update repository configuration')
    } finally {
      setLoading(false)
    }
  }

  // Check if form data has changed from original values
  const hasChanges = 
    formData.gitRepoUrl !== (project.gitRepoUrl || '') ||
    formData.branch !== (project.branch || 'main') ||
    formData.subdirectory !== (project.subdirectory || '') ||
    formData.port !== (project.port || 3000) ||
    formData.healthCheckPath !== (project.healthCheckPath || '/health')

  const isDeploying = project.status === 'DEPLOYING' || project.status === 'BUILDING' || project.status === 'CLONING'
  
  // Some fields should be locked during deployment, others can be modified
  const shouldLockRepoFields = isDeploying // Repository URL, branch, subdirectory - affect build
  const shouldLockRuntimeFields = false // Health check, port - can be updated live

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
          <div className="relative">
            <input
              type="url"
              id="gitRepoUrl"
              value={formData.gitRepoUrl}
              onChange={(e) => handleRepoUrlChange(e.target.value)}
              disabled={shouldLockRepoFields}
              className={`w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed ${repoInfo ? 'pr-10' : ''}`}
              placeholder="https://github.com/username/repository"
              required
            />
            {validating && (
              <div className="absolute inset-y-0 right-0 flex items-center pr-3">
                <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
              </div>
            )}
            {repoInfo && !validating && (
              <div className="absolute inset-y-0 right-0 flex items-center pr-3">
                <CheckCircle className="h-4 w-4 text-green-500" />
              </div>
            )}
          </div>
          {repoInfo && (
            <div className="mt-2 p-3 bg-green-50 border border-green-200 rounded-lg">
              <div className="flex items-center space-x-2 text-sm text-green-800">
                <CheckCircle className="h-4 w-4" />
                <span className="font-medium">Repository validated</span>
              </div>
              <div className="mt-1 text-sm text-green-700">
                <div className="flex items-center space-x-2">
                  <GitBranch className="h-3 w-3" />
                  <span>{repoInfo.fullName}</span>
                  {repoInfo.private && (
                    <span className="px-1.5 py-0.5 bg-green-100 text-green-700 text-xs rounded">Private</span>
                  )}
                </div>
                {repoInfo.description && (
                  <p className="mt-1 text-xs">{repoInfo.description}</p>
                )}
              </div>
            </div>
          )}
          <p className="text-xs text-gray-500 mt-1">GitHub repository URL for your project</p>
        </div>

        <div>
          <label htmlFor="branch" className="block text-sm font-medium text-gray-700 mb-2">
            Branch
          </label>
          {branches.length > 0 ? (
            <Select
              value={formData.branch}
              onValueChange={(value) => setFormData({ ...formData, branch: value })}
              disabled={shouldLockRepoFields}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select a branch" />
              </SelectTrigger>
              <SelectContent>
                {branches.map((branch) => (
                  <SelectItem key={branch} value={branch}>
                    <div className="flex items-center space-x-2">
                      <GitBranch className="h-3 w-3" />
                      <span>{branch}</span>
                      {repoInfo?.defaultBranch === branch && (
                        <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 text-xs rounded">Default</span>
                      )}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <input
              type="text"
              id="branch"
              value={formData.branch}
              onChange={(e) => setFormData({ ...formData, branch: e.target.value })}
              disabled={shouldLockRepoFields}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
              placeholder="main"
              required
            />
          )}
          <p className="text-xs text-gray-500 mt-1">
            {branches.length > 0 
              ? `Choose from ${branches.length} available branches` 
              : 'Git branch to deploy from'
            }
          </p>
        </div>

        <div>
          <label htmlFor="subdirectory" className="block text-sm font-medium text-gray-700 mb-2">
            Subdirectory (Optional)
          </label>
          <input
            type="text"
            id="subdirectory"
            value={formData.subdirectory}
            onChange={(e) => setFormData({ ...formData, subdirectory: e.target.value })}
            disabled={shouldLockRepoFields}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            placeholder="e.g., backend or apps/api"
          />
          <p className="text-xs text-gray-500 mt-1">Path to the subdirectory containing your Dockerfile (leave empty for root)</p>
        </div>

        <div>
          <label htmlFor="port" className="block text-sm font-medium text-gray-700 mb-2">
            Application Port
          </label>
          <input
            type="number"
            id="port"
            value={formData.port}
            onChange={(e) => setFormData({ ...formData, port: parseInt(e.target.value) || 3000 })}
            disabled={shouldLockRuntimeFields}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            placeholder="3000"
            required
          />
          <p className="text-xs text-gray-500 mt-1">The port your application listens on</p>
        </div>

        <div>
          <label htmlFor="healthCheckPath" className="block text-sm font-medium text-gray-700 mb-2">
            Health Check Path
          </label>
          <input
            type="text"
            id="healthCheckPath"
            value={formData.healthCheckPath}
            onChange={(e) => setFormData({ ...formData, healthCheckPath: e.target.value })}
            disabled={shouldLockRuntimeFields}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            placeholder="/health"
            required
          />
          <p className="text-xs text-gray-500 mt-1">The endpoint used by the load balancer to check application health</p>
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

        {shouldLockRepoFields && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <p className="text-yellow-800">
              Repository URL, branch, and subdirectory are locked during deployment. 
              Health check path and port can still be modified.
            </p>
          </div>
        )}

        <div className="flex space-x-4">
          <Button
            type="submit"
            disabled={loading || !hasChanges}
          >
            {loading ? 'Saving...' : 'Save Changes'}
          </Button>
        </div>
      </form>

      <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
        <h4 className="font-medium text-blue-900 mb-2">ℹ️ Configuration Updates</h4>
        <div className="text-sm text-blue-800 space-y-1">
          <p><strong>Health check path & port:</strong> Updates take effect immediately on deployed services.</p>
          <p><strong>Repository changes:</strong> Require a new deployment to take effect.</p>
        </div>
      </div>

      {/* Auto-deploy section */}
      <div className="mt-8 border-t pt-8">
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-gray-900">Automatic Deployments</h3>
          <p className="text-sm text-gray-600 mt-1">
            Enable automatic deployments when commits are pushed to the <strong>{formData.branch}</strong> branch.
          </p>
        </div>

        {/* Auto-deploy toggle */}
        <div className="flex items-center justify-between p-4 border border-gray-200 rounded-lg">
          <div>
            <h4 className="font-medium text-gray-900">Auto-deploy on push</h4>
            <p className="text-sm text-gray-600">
              Automatically deploy when commits are pushed to {formData.branch}
            </p>
          </div>
          <Switch
            checked={autoDeployEnabled}
            onCheckedChange={handleAutoDeployToggle}
            disabled={webhookLoading}
          />
        </div>

        {/* Webhook configuration */}
        {autoDeployEnabled && (
          <div className="mt-4 border border-gray-200 rounded-lg p-4 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Webhook className="h-5 w-5 text-gray-500" />
                <h4 className="font-medium text-gray-900">GitHub Webhook</h4>
                {webhookConfigured && (
                  <span className="flex items-center text-sm text-green-600">
                    <CheckCircle className="h-4 w-4 mr-1" />
                    Configured
                  </span>
                )}
              </div>
              <div className="flex space-x-2">
                {!webhookConfig && !webhookConfigured && (
                  <Button
                    onClick={configureWebhook}
                    disabled={webhookLoading}
                    size="sm"
                  >
                    Configure Webhook
                  </Button>
                )}
                {webhookConfigured && !webhookConfig && (
                  <Button
                    onClick={configureWebhook}
                    disabled={webhookLoading}
                    variant="outline"
                    size="sm"
                  >
                    Re-configure
                  </Button>
                )}
                {(webhookConfig || webhookConfigured) && (
                  <>
                    {webhookConfig && !webhookConfig.automatic && (
                      <Button
                        onClick={() => setShowWebhookInstructions(!showWebhookInstructions)}
                        variant="outline"
                        size="sm"
                      >
                        {showWebhookInstructions ? 'Hide' : 'Show'} Instructions
                      </Button>
                    )}
                    <Button
                      onClick={openGitHubSettings}
                      variant="outline"
                      size="sm"
                    >
                      <ExternalLink className="h-4 w-4 mr-1" />
                      GitHub Settings
                    </Button>
                    <Button
                      onClick={deleteWebhookConfig}
                      variant="destructive"
                      size="sm"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </>
                )}
              </div>
            </div>

            {webhookConfig && (
              <div className="space-y-4">
                {/* Webhook URL */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Webhook URL
                  </label>
                  <div className="flex items-center space-x-2">
                    <input
                      type="text"
                      value={webhookConfig.webhookUrl}
                      readOnly
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-sm font-mono"
                    />
                    <Button
                      onClick={() => copyToClipboard(webhookConfig.webhookUrl)}
                      variant="outline"
                      size="sm"
                    >
                      <Copy className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                {/* Webhook Secret */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Webhook Secret
                  </label>
                  <div className="flex items-center space-x-2">
                    <input
                      type="password"
                      value={webhookConfig.webhookSecret}
                      readOnly
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-sm font-mono"
                    />
                    <Button
                      onClick={() => copyToClipboard(webhookConfig.webhookSecret)}
                      variant="outline"
                      size="sm"
                    >
                      <Copy className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                {/* Setup Instructions */}
                {showWebhookInstructions && webhookConfig.instructions && (
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <h5 className="font-medium text-blue-900 mb-2">Setup Instructions</h5>
                    <ol className="text-sm text-blue-800 space-y-1">
                      {Object.entries(webhookConfig.instructions).map(([step, instruction]) => (
                        <li key={step} className="flex">
                          <span className="font-medium mr-2">{step}.</span>
                          <span>{instruction}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>
            )}

            {!webhookConfig && !webhookConfigured && (
              <div className="flex items-start space-x-2 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                <AlertCircle className="h-5 w-5 text-yellow-600 mt-0.5" />
                <div className="text-sm text-yellow-800">
                  <p className="font-medium">Webhook not configured</p>
                  <p>Click "Configure Webhook" to set up automatic deployments.</p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Info box */}
        <div className="mt-4 bg-gray-50 border border-gray-200 rounded-lg p-4">
          <h5 className="font-medium text-gray-900 mb-2">How it works</h5>
          <ul className="text-sm text-gray-600 space-y-1">
            <li>• Webhook listens for push events to the <strong>{formData.branch}</strong> branch</li>
            <li>• Only commits to this specific branch trigger deployments</li>
            <li>• Deployments are queued if one is already in progress</li>
            <li>• You can still manually deploy from any branch</li>
          </ul>
        </div>
      </div>
    </div>
  )
}