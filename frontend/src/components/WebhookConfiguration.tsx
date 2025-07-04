'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import { Project } from '@/types'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Webhook, Copy, Trash2, ExternalLink, AlertCircle, CheckCircle } from 'lucide-react'
import { apiClient } from '@/lib/api'

interface WebhookConfigurationProps {
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

export default function WebhookConfiguration({ projectId, project, onUpdate }: WebhookConfigurationProps) {
  const { data: session } = useSession()
  const [autoDeployEnabled, setAutoDeployEnabled] = useState(project.autoDeployEnabled || false)
  const [webhookConfig, setWebhookConfig] = useState<WebhookConfig | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [showInstructions, setShowInstructions] = useState(false)
  const [webhookConfigured, setWebhookConfigured] = useState(project.webhookConfigured || false)

  // Update webhookConfigured when project prop changes
  useEffect(() => {
    setWebhookConfigured(project.webhookConfigured || false)
  }, [project.webhookConfigured])

  const handleAutoDeployToggle = async (enabled: boolean) => {
    setLoading(true)
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
      setLoading(false)
    }
  }

  const configureWebhook = async () => {
    setLoading(true)
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
        setShowInstructions(true)
        setSuccess('Webhook configuration generated! Please follow the instructions to complete setup.')
      }
    } catch (err) {
      setError('Failed to configure webhook')
    } finally {
      setLoading(false)
    }
  }

  const deleteWebhookConfig = async () => {
    if (!confirm('Are you sure you want to delete the webhook configuration? This will disable auto-deploy.')) {
      return
    }

    setLoading(true)
    setError('')

    try {
      // Pass GitHub access token to delete from GitHub too
      await apiClient.deleteWebhookConfig(projectId, session?.accessToken)
      setWebhookConfig(null)
      setAutoDeployEnabled(false)
      setWebhookConfigured(false)
      setShowInstructions(false)
      setSuccess('Webhook configuration deleted!')
      onUpdate()
    } catch (err) {
      setError('Failed to delete webhook configuration')
    } finally {
      setLoading(false)
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
    if (project.gitRepoUrl) {
      const settingsUrl = `${project.gitRepoUrl}/settings/hooks`
      window.open(settingsUrl, '_blank')
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900 mb-2">Automatic Deployments</h2>
        <p className="text-gray-600 text-sm mb-4">
          Enable automatic deployments when commits are pushed to the <strong>{project.branch}</strong> branch.
        </p>
      </div>

      {/* Auto-deploy toggle */}
      <div className="flex items-center justify-between p-4 border border-gray-200 rounded-lg">
        <div>
          <h3 className="font-medium text-gray-900">Auto-deploy on push</h3>
          <p className="text-sm text-gray-600">
            Automatically deploy when commits are pushed to {project.branch}
          </p>
        </div>
        <Switch
          checked={autoDeployEnabled}
          onCheckedChange={handleAutoDeployToggle}
          disabled={loading}
        />
      </div>

      {/* Webhook configuration */}
      {autoDeployEnabled && (
        <div className="border border-gray-200 rounded-lg p-4 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Webhook className="h-5 w-5 text-gray-500" />
              <h3 className="font-medium text-gray-900">GitHub Webhook</h3>
              {webhookConfigured && (
                <span className="flex items-center text-sm text-success-foreground">
                  <CheckCircle className="h-4 w-4 mr-1" />
                  Configured
                </span>
              )}
            </div>
            <div className="flex space-x-2">
              {!webhookConfig && !webhookConfigured && (
                <Button
                  onClick={configureWebhook}
                  disabled={loading}
                  size="sm"
                >
                  Configure Webhook
                </Button>
              )}
              {webhookConfigured && !webhookConfig && (
                <Button
                  onClick={configureWebhook}
                  disabled={loading}
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
                      onClick={() => setShowInstructions(!showInstructions)}
                      variant="outline"
                      size="sm"
                    >
                      {showInstructions ? 'Hide' : 'Show'} Instructions
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
              {showInstructions && webhookConfig.instructions && (
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                  <h4 className="font-medium text-blue-900 mb-2">Setup Instructions</h4>
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

          {!webhookConfig && (
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

      {/* Status messages */}
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
    </div>
  )
}