'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { apiClient } from '@/lib/api'
import { Key, Shield, TestTube, Trash2, AlertCircle, CheckCircle, Eye, EyeOff } from 'lucide-react'

interface TeamAwsConfig {
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
  const [config, setConfig] = useState<TeamAwsConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [showSecrets, setShowSecrets] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isTesting, setIsTesting] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [testResult, setTestResult] = useState<any>(null)

  // Form state
  const [formData, setFormData] = useState({
    awsAccessKeyId: '',
    awsSecretAccessKey: '',
    awsRegion: 'us-east-1'
  })

  useEffect(() => {
    fetchAwsConfig()
  }, [teamId])

  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => setSuccess(''), 5000)
      return () => clearTimeout(timer)
    }
  }, [success])

  const fetchAwsConfig = async () => {
    try {
      setLoading(true)
      const data = await apiClient.getTeamAwsConfig(teamId)
      setConfig(data)
    } catch (error: any) {
      if (error.message.includes('404')) {
        // No config exists yet
        setConfig(null)
      } else {
        setError('Failed to load AWS configuration')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    setError('')
    setSuccess('')

    try {
      await apiClient.createTeamAwsConfig(teamId, formData)
      setSuccess('AWS credentials saved successfully')
      setShowForm(false)
      setFormData({ awsAccessKeyId: '', awsSecretAccessKey: '', awsRegion: 'us-east-1' })
      await fetchAwsConfig()
    } catch (error: any) {
      setError(error.message || 'Failed to save AWS credentials')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleTest = async () => {
    setIsTesting(true)
    setError('')
    setTestResult(null)

    try {
      const result = await apiClient.testTeamAwsConfig(teamId)
      setTestResult(result)
    } catch (error: any) {
      // Handle different types of errors based on message content
      const errorMessage = error.message || 'Failed to test AWS credentials'
      
      if (errorMessage.includes('lack sufficient permissions') || 
          errorMessage.includes('not authorized to perform') ||
          errorMessage.includes('permission to list S3 buckets')) {
        setTestResult({
          success: false,
          permissionIssue: true,
          message: errorMessage
        })
      } else {
        setError(errorMessage)
      }
    } finally {
      setIsTesting(false)
    }
  }

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete the AWS configuration? This will affect all team deployments.')) {
      return
    }

    setIsDeleting(true)
    setError('')

    try {
      await apiClient.deleteTeamAwsConfig(teamId)
      setSuccess('AWS configuration deleted successfully')
      setConfig(null)
      setTestResult(null)
    } catch (error: any) {
      setError(error.message || 'Failed to delete AWS configuration')
    } finally {
      setIsDeleting(false)
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
        <p className="text-gray-600 mt-2">Loading AWS configuration...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium text-gray-900 flex items-center">
            <Key className="h-5 w-5 mr-2" />
            AWS Configuration
          </h3>
          <p className="text-sm text-gray-600 mt-1">
            Configure team AWS credentials for deployments and infrastructure management
          </p>
        </div>
        {config && !showForm && (
          <div className="flex space-x-2">
            <Button variant="outline" onClick={handleTest} disabled={isTesting}>
              <TestTube className="h-4 w-4 mr-2" />
              {isTesting ? 'Testing...' : 'Test Connection'}
            </Button>
            <Button variant="outline" onClick={() => setShowForm(true)}>
              Update Credentials
            </Button>
          </div>
        )}
      </div>

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

      {config && !showForm ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span className="flex items-center">
                <Shield className="h-5 w-5 mr-2 text-green-600" />
                AWS Credentials Configured
              </span>
              <Badge variant="outline" className="bg-green-50 text-green-700">
                Active
              </Badge>
            </CardTitle>
            <CardDescription>
              Your team is using custom AWS credentials for deployments
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label className="text-sm font-medium text-gray-700">Access Key ID</Label>
                <div className="flex items-center space-x-2 mt-1">
                  <Input
                    type={showSecrets ? 'text' : 'password'}
                    value={config.awsAccessKeyId}
                    readOnly
                    className="bg-gray-50"
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowSecrets(!showSecrets)}
                  >
                    {showSecrets ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
              <div>
                <Label className="text-sm font-medium text-gray-700">Secret Access Key</Label>
                <div className="flex items-center space-x-2 mt-1">
                  <Input
                    type="password"
                    value={config.awsSecretAccessKey}
                    readOnly
                    className="bg-gray-50"
                  />
                </div>
              </div>
              <div>
                <Label className="text-sm font-medium text-gray-700">Region</Label>
                <Input
                  value={getRegionLabel(config.awsRegion)}
                  readOnly
                  className="bg-gray-50 mt-1"
                />
              </div>
              <div>
                <Label className="text-sm font-medium text-gray-700">Last Updated</Label>
                <Input
                  value={new Date(config.updatedAt).toLocaleDateString()}
                  readOnly
                  className="bg-gray-50 mt-1"
                />
              </div>
            </div>

            {testResult && (
              <div className={`mt-4 p-4 rounded-lg border ${
                testResult.permissionIssue 
                  ? 'bg-yellow-50 border-yellow-200' 
                  : 'bg-green-50 border-green-200'
              }`}>
                <h4 className={`text-sm font-medium mb-2 ${
                  testResult.permissionIssue 
                    ? 'text-yellow-900' 
                    : 'text-green-900'
                }`}>
                  {testResult.permissionIssue 
                    ? '⚠️ Credentials Valid, Limited Permissions' 
                    : '✅ Connection Test Successful'
                  }
                </h4>
                <div className={`text-sm space-y-1 ${
                  testResult.permissionIssue 
                    ? 'text-yellow-700' 
                    : 'text-green-700'
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
            )}

            <div className="flex justify-end pt-4">
              <Button
                variant="outline"
                onClick={handleDelete}
                disabled={isDeleting}
                className="text-red-600 border-red-300 hover:bg-red-50"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                {isDeleting ? 'Deleting...' : 'Delete Configuration'}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : showForm || !config ? (
        <Card>
          <CardHeader>
            <CardTitle>
              {config ? 'Update AWS Credentials' : 'Configure AWS Credentials'}
            </CardTitle>
            <CardDescription>
              Enter your AWS credentials to enable team deployments. These will be encrypted and stored securely.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <Label htmlFor="accessKeyId">AWS Access Key ID</Label>
                <Input
                  id="accessKeyId"
                  type="text"
                  value={formData.awsAccessKeyId}
                  onChange={(e) => setFormData({ ...formData, awsAccessKeyId: e.target.value })}
                  placeholder="AKIA..."
                  required
                  className="mt-1"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Your AWS Access Key ID (starts with AKIA)
                </p>
              </div>

              <div>
                <Label htmlFor="secretAccessKey">AWS Secret Access Key</Label>
                <Input
                  id="secretAccessKey"
                  type="password"
                  value={formData.awsSecretAccessKey}
                  onChange={(e) => setFormData({ ...formData, awsSecretAccessKey: e.target.value })}
                  placeholder="Enter your secret access key"
                  required
                  className="mt-1"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Your AWS Secret Access Key (will be encrypted)
                </p>
              </div>

              <div>
                <Label htmlFor="region">AWS Region</Label>
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
                  Primary AWS region for deployments
                </p>
              </div>

              <div className="flex space-x-2 pt-4">
                <Button
                  type="submit"
                  disabled={isSubmitting || !formData.awsAccessKeyId || !formData.awsSecretAccessKey}
                >
                  {isSubmitting ? 'Saving...' : config ? 'Update Credentials' : 'Save Credentials'}
                </Button>
                {(showForm && config) && (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                      setShowForm(false)
                      setFormData({ awsAccessKeyId: '', awsSecretAccessKey: '', awsRegion: 'us-east-1' })
                    }}
                  >
                    Cancel
                  </Button>
                )}
              </div>
            </form>
          </CardContent>
        </Card>
      ) : null}

      {!config && !showForm && (
        <Card>
          <CardContent className="text-center py-8">
            <Key className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No AWS Configuration</h3>
            <p className="text-gray-600 mb-4">
              Configure AWS credentials to enable team deployments with your own AWS account.
            </p>
            <Button onClick={() => setShowForm(true)}>
              <Key className="h-4 w-4 mr-2" />
              Configure AWS Credentials
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h4 className="text-sm font-medium text-blue-900 mb-2">Security Information</h4>
        <ul className="text-sm text-blue-700 space-y-1">
          <li>• AWS credentials are encrypted using AES-256 encryption before storage</li>
          <li>• Only team owners can view and manage AWS credentials</li>
          <li>• Credentials are used exclusively for team project deployments</li>
          <li>• You can test your credentials at any time to verify they're working</li>
        </ul>
      </div>
    </div>
  )
}