'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import { Project } from '@/types'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { CheckCircle, GitBranch, Loader2, Webhook, Copy, Trash2, ExternalLink, AlertCircle } from 'lucide-react'
import { apiClient } from '@/lib/api'
import { FormInput } from '@/components/ui/FormInput'

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

  // Update webhookConfigured when project prop changes
  useEffect(() => {
    setWebhookConfigured(project.webhookConfigured || false)
  }, [project.webhookConfigured])

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

  const isDeploying = false // Status is now at environment level
  
  // Some fields should be locked during deployment, others can be modified
  const shouldLockRepoFields = isDeploying // Repository URL, branch, subdirectory - affect build
  const shouldLockRuntimeFields = false // Health check, port - can be updated live

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg text-foreground">Repository Configuration</h2>
      </div>
      
      <form onSubmit={handleSubmit} className="space-y-6">
        <FormInput
          id="gitRepoUrl"
          label="Repository URL"
          type="url"
          value={formData.gitRepoUrl}
          onChange={(value) => handleRepoUrlChange(value as string)}
          disabled={shouldLockRepoFields}
          placeholder="https://github.com/username/repository"
          helpText="GitHub repository URL for your project"
          required
          rightElement={
            validating ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : repoInfo ? (
              <CheckCircle className="h-4 w-4 text-green-500" />
            ) : null
          }
          bottomElement={
            repoInfo && (
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
            )
          }
        />

        <FormInput
          id="subdirectory"
          label="Subdirectory (Optional)"
          value={formData.subdirectory}
          onChange={(value) => setFormData({ ...formData, subdirectory: value as string })}
          disabled={shouldLockRepoFields}
          placeholder="e.g., backend or apps/api"
          helpText="Path to the subdirectory containing your Dockerfile (leave empty for root)"
        />

        <FormInput
          id="port"
          label="Application Port"
          type="number"
          value={formData.port}
          onChange={(value) => setFormData({ ...formData, port: value as number })}
          disabled={shouldLockRuntimeFields}
          placeholder="3000"
          helpText="The port your application listens on"
          required
        />

        <FormInput
          id="healthCheckPath"
          label="Health Check Path"
          value={formData.healthCheckPath}
          onChange={(value) => setFormData({ ...formData, healthCheckPath: value as string })}
          disabled={shouldLockRuntimeFields}
          placeholder="/health"
          helpText="The endpoint used by the load balancer to check application health"
          required
        />

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

      {/* Auto-deploy section */}
      <div className="mt-8 border-t pt-8">
        <div className="mb-4 w-full flex">
          <div className="flex-1">
            <h3 className="text-lg font-semibold">Automatic Deployments</h3>
            <p className="text-sm mt-1">
              Deploy environments automatically when commits are pushed to the configured branches.
            </p>
          </div>
          <Switch
            className="w-10"
            checked={autoDeployEnabled}
            onCheckedChange={handleAutoDeployToggle}
            disabled={webhookLoading}
          />
        </div>
        
        {/* Webhook configuration */}
        {autoDeployEnabled && (
          <div className="mt-4 border border-gray-700 rounded p-4 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Webhook className="h-5 w-5" />
                <h4 className="font-medium">GitHub Webhook</h4>
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
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg bg-primary text-sm font-mono"
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
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg bg-primary text-sm font-mono"
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
      </div>
    </div>
  )
}