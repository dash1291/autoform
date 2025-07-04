'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
// Dialog component will be replaced with conditional rendering
import { apiClient } from '@/lib/api'
import { Key, Shield, TestTube, Trash2, AlertCircle, CheckCircle, BookOpen, ExternalLink, Plus, Settings } from 'lucide-react'

interface TeamAwsConfig {
  id: string
  name: string
  awsAccessKeyId: string // This will be masked from the API
  awsSecretAccessKey: string // This will be masked from the API
  awsRegion: string
  isActive: boolean
  createdAt: string
  updatedAt: string
}

interface TeamAwsConfigurationProps {
  teamId: string
}

const AWS_REGIONS = [
  { value: 'us-east-1', label: 'US East (N. Virginia)' },
  { value: 'us-east-2', label: 'US East (Ohio)' },
  { value: 'us-west-1', label: 'US West (N. California)' },
  { value: 'us-west-2', label: 'US West (Oregon)' },
  { value: 'eu-west-1', label: 'Europe (Ireland)' },
  { value: 'eu-west-2', label: 'Europe (London)' },
  { value: 'eu-west-3', label: 'Europe (Paris)' },
  { value: 'eu-central-1', label: 'Europe (Frankfurt)' },
  { value: 'ap-southeast-1', label: 'Asia Pacific (Singapore)' },
  { value: 'ap-southeast-2', label: 'Asia Pacific (Sydney)' },
  { value: 'ap-northeast-1', label: 'Asia Pacific (Tokyo)' },
  { value: 'ap-south-1', label: 'Asia Pacific (Mumbai)' },
]

export default function TeamAwsConfiguration({ teamId }: TeamAwsConfigurationProps) {
  const [configs, setConfigs] = useState<TeamAwsConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isTesting, setIsTesting] = useState<string | null>(null)
  const [isDeleting, setIsDeleting] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [testResult, setTestResult] = useState<any>(null)
  const [showForm, setShowForm] = useState(false)
  const [editingConfig, setEditingConfig] = useState<TeamAwsConfig | null>(null)

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    awsAccessKeyId: '',
    awsSecretAccessKey: '',
    awsRegion: 'us-east-1'
  })

  useEffect(() => {
    fetchAwsConfigs()
  }, [teamId])

  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => setSuccess(''), 5000)
      return () => clearTimeout(timer)
    }
  }, [success])

  const fetchAwsConfigs = async () => {
    try {
      setLoading(true)
      try {
        const data = await apiClient.getTeamAwsConfigs(teamId)
        setConfigs(data || [])
      } catch (error: any) {
        if (error.message.includes('404')) {
          setConfigs([])
        } else {
          throw error
        }
      }
    } catch (error: any) {
      setError('Failed to load AWS configurations')
    } finally {
      setLoading(false)
    }
  }

  const openCreateForm = () => {
    setEditingConfig(null)
    setFormData({
      name: '',
      awsAccessKeyId: '',
      awsSecretAccessKey: '',
      awsRegion: 'us-east-1'
    })
    setShowForm(true)
  }

  const openEditForm = (config: TeamAwsConfig) => {
    setEditingConfig(config)
    setFormData({
      name: config.name,
      awsAccessKeyId: config.awsAccessKeyId,
      awsSecretAccessKey: '••••••••••••••••••••', // Show masked placeholder
      awsRegion: config.awsRegion
    })
    setShowForm(true)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    setError('')
    setSuccess('')

    try {
      // Prepare data for submission
      const submitData = {
        name: formData.name,
        awsAccessKeyId: formData.awsAccessKeyId,
        awsSecretAccessKey: formData.awsSecretAccessKey,
        awsRegion: formData.awsRegion
      }

      // If updating existing config and secret key wasn't changed, don't send masked value
      if (editingConfig && formData.awsSecretAccessKey === '••••••••••••••••••••') {
        // Only update other fields, keep existing secret
        submitData.awsSecretAccessKey = '' // Backend will handle keeping existing value
      }

      if (editingConfig) {
        await apiClient.updateTeamAwsConfig(teamId, editingConfig.id, submitData)
      } else {
        await apiClient.createTeamAwsConfig(teamId, submitData)
      }
      setSuccess(`AWS configuration "${formData.name}" ${editingConfig ? 'updated' : 'created'} successfully`)
      setShowForm(false)
      await fetchAwsConfigs()
    } catch (error: any) {
      setError(error.message || 'Failed to save AWS configuration')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleTest = async (configId: string) => {
    setIsTesting(configId)
    setError('')
    setTestResult(null)

    try {
      const result = await apiClient.testTeamAwsConfig(teamId, configId)
      setTestResult({ 
        ...result as any, 
        configId 
      })
    } catch (error: any) {
      const errorMessage = error.message || 'Failed to test AWS credentials'
      
      if (errorMessage.includes('404') || errorMessage.includes('not found')) {
        setError('Please save your credentials before testing the connection')
      } else if (errorMessage.includes('lack sufficient permissions') || 
          errorMessage.includes('not authorized to perform') ||
          errorMessage.includes('permission to list S3 buckets')) {
        setTestResult({
          configId,
          success: false,
          permissionIssue: true,
          message: errorMessage
        })
      } else {
        setError(errorMessage)
      }
    } finally {
      setIsTesting(null)
    }
  }

  const handleDelete = async (config: TeamAwsConfig) => {
    if (!confirm(`Are you sure you want to delete the AWS configuration "${config.name}"? This may affect team deployments using this configuration.`)) {
      return
    }

    setIsDeleting(config.id)
    setError('')

    try {
      await apiClient.deleteTeamAwsConfig(teamId, config.id)
      setSuccess(`AWS configuration "${config.name}" deleted successfully`)
      setTestResult(null)
      await fetchAwsConfigs()
    } catch (error: any) {
      setError(error.message || 'Failed to delete AWS configuration')
    } finally {
      setIsDeleting(null)
    }
  }

  const getRegionLabel = (regionValue: string) => {
    const region = AWS_REGIONS.find(r => r.value === regionValue)
    return region ? region.label : regionValue
  }

  if (loading) {
    return (
      <div className="text-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
        <p className="text-gray-600 mt-2">Loading AWS configurations...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {success && (
        <Alert>
          <CheckCircle className="h-4 w-4" />
          <AlertDescription>{success}</AlertDescription>
        </Alert>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg">AWS Configurations</h2>
          <p className="text-gray-600 text-sm mt-0.5">
            Manage multiple AWS credential sets for different environments
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Button variant="outline" size="sm" asChild>
            <a href="/docs" target="_blank" rel="noopener noreferrer">
              <BookOpen className="h-4 w-4 mr-2" />
              Setup Guide
              <ExternalLink className="h-3 w-3 ml-1" />
            </a>
          </Button>
          <Button size="sm" onClick={openCreateForm}>
            <Plus className="h-3 w-3 mr-2" />
            Add Configuration
          </Button>
        </div>
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>
              {editingConfig ? 'Edit AWS Configuration' : 'Add AWS Configuration'}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <Label>Configuration Name</Label>
                <Input
                  type="text"
                  value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g., Production, Staging, Development"
                  required
                  className="mt-1"
                />
                <p className="text-xs text-gray-500 mt-1">
                  A descriptive name for this configuration
                </p>
              </div>

              <div>
                <Label>AWS Access Key ID</Label>
                <Input
                  type="text"
                  value={formData.awsAccessKeyId}
                  onChange={(e) => setFormData({ ...formData, awsAccessKeyId: e.target.value })}
                  placeholder={editingConfig ? "AKIA••••••••••••••••" : "AKIA..."}
                  autoComplete="new-password"
                  data-lpignore="true"
                  required
                  className="mt-1"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Your AWS Access Key ID
                </p>
              </div>

              <div>
                <Label>AWS Secret Access Key</Label>
                <Input
                  type="password"
                  value={formData.awsSecretAccessKey}
                  onChange={(e) => setFormData({ ...formData, awsSecretAccessKey: e.target.value })}
                  placeholder={editingConfig ? "••••••••••••••••••••••••••••••••••••••••" : "Enter your secret access key"}
                  autoComplete="new-password"
                  data-lpignore="true"
                  required
                  className="mt-1"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Your AWS Secret Access Key (will be encrypted)
                </p>
              </div>

              <div>
                <Label>AWS Region</Label>
                <Select
                  value={formData.awsRegion}
                  onValueChange={(value) => setFormData({ ...formData, awsRegion: value })}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue placeholder="Select a region" />
                  </SelectTrigger>
                  <SelectContent>
                    {AWS_REGIONS.map((region) => (
                      <SelectItem key={region.value} value={region.value}>
                        {region.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-gray-500 mt-1">
                  Primary AWS region for this configuration
                </p>
              </div>

              <div className="flex justify-end space-x-2 pt-4">
                <Button type="button" variant="outline" onClick={() => setShowForm(false)}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={isSubmitting || !formData.name || !formData.awsAccessKeyId || (!formData.awsSecretAccessKey && !editingConfig)}
                >
                  {isSubmitting ? 'Saving...' : editingConfig ? 'Update Configuration' : 'Save Configuration'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {configs.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Key className="h-12 w-12 text-gray-400 mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No AWS Configurations</h3>
            <p className="text-gray-500 text-center mb-6 max-w-md">
              Add your first AWS configuration to enable team deployments and infrastructure management.
            </p>
            <Button onClick={openCreateForm}>
              <Plus className="h-4 w-4 mr-2" />
              Add Your First Configuration
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {configs.map((config) => (
            <Card key={config.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex text-sm items-center">
                      {config.name}
                    </CardTitle>
                    <CardDescription className="mt-1 text-xs">
                      Region: {getRegionLabel(config.awsRegion)} • Access Key: {config.awsAccessKeyId}
                    </CardDescription>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Badge variant="outline" className="bg-green-50 text-green-700">
                      {config.isActive ? 'Active' : 'Inactive'}
                    </Badge>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      onClick={() => handleTest(config.id)} 
                      disabled={isTesting === config.id}
                    >
                      <TestTube className="h-4 w-4 mr-2" />
                      {isTesting === config.id ? 'Testing...' : 'Test'}
                    </Button>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      onClick={() => openEditForm(config)}
                    >
                      <Settings className="h-4 w-4 mr-2" />
                      Edit
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDelete(config)}
                      disabled={isDeleting === config.id}
                      className="text-destructive border-destructive hover:bg-destructive"
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      {isDeleting === config.id ? 'Deleting...' : 'Delete'}
                    </Button>
                  </div>
                </div>
              </CardHeader>
              {testResult && testResult.configId === config.id && (
                <CardContent>
                  <div className={`bg-background border-gray-700 p-4 rounded border`}>
                    <h4 className={`text-sm font-medium mb-2 ${
                      testResult.permissionIssue
                        ? 'text-yellow-300' 
                        : 'text-green-300'
                    }`}>
                      {testResult.permissionIssue 
                        ? '⚠️ Credentials Valid, Limited Permissions' 
                        : '✅ Connection Test Successful'
                      }
                    </h4>
                    <div className={`text-sm space-y-1 ${
                      testResult.permissionIssue 
                        ? 'text-yellow-300' 
                        : 'text-green-300'
                    }`}>
                      {testResult.permissionIssue ? (
                        <p>{testResult.message}</p>
                      ) : (
                        <>
                          <p>Account ID: {testResult.accountId}</p>
                          <p>Region: {testResult.region}</p>
                          <p>S3 Buckets Found: {testResult.bucketCount}</p>
                          {testResult.arn && <p>User/Role: {testResult.arn}</p>}
                        </>
                      )}
                    </div>
                  </div>
                </CardContent>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}