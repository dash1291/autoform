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

interface UserAwsConfig {
  accessKeyId: string // This will be masked from the API
  region: string
  configured: boolean
  createdAt?: string
  updatedAt?: string
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

export default function UserAwsConfiguration() {
  const [config, setConfig] = useState<UserAwsConfig | null>(null)
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
    accessKeyId: '',
    secretAccessKey: '',
    region: 'us-east-1'
  })

  useEffect(() => {
    fetchAwsConfig()
  }, [])

  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => setSuccess(''), 5000)
      return () => clearTimeout(timer)
    }
  }, [success])

  const fetchAwsConfig = async () => {
    try {
      setLoading(true)
      const data = await apiClient.getUserAwsConfig()
      setConfig(data)
    } catch (error: any) {
      if (error.message.includes('404') || !error.configured) {
        // No config exists yet
        setConfig({ configured: false, accessKeyId: '', region: '' })
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
      await apiClient.saveUserAwsConfig(formData)
      setSuccess('AWS credentials saved successfully')
      setShowForm(false)
      setFormData({ accessKeyId: '', secretAccessKey: '', region: 'us-east-1' })
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
      const result = await apiClient.testAwsCredentials('personal')
      setTestResult(result)
    } catch (error: any) {
      const errorMessage = error.message || 'Failed to test AWS credentials'
      
      if (errorMessage.includes('lack sufficient permissions') || 
          errorMessage.includes('not authorized to perform') ||
          errorMessage.includes('AccessDenied')) {
        setTestResult({
          status: 'partial',
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
    if (!confirm('Are you sure you want to delete your AWS configuration? This will affect your personal project deployments.')) {
      return
    }

    setIsDeleting(true)
    setError('')

    try {
      await apiClient.deleteUserAwsConfig()
      setSuccess('AWS configuration deleted successfully')
      setConfig({ configured: false, accessKeyId: '', region: '' })
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

      {config?.configured && !showForm ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <Shield className="h-5 w-5 mr-2 text-green-600" />
              <span className="font-medium text-gray-900">AWS Credentials Configured</span>
              <Badge variant="outline" className="bg-green-50 text-green-700 ml-2">
                Active
              </Badge>
            </div>
            <div className="flex space-x-2">
              <Button variant="outline" onClick={handleTest} disabled={isTesting}>
                <TestTube className="h-4 w-4 mr-2" />
                {isTesting ? 'Testing...' : 'Test Connection'}
              </Button>
              <Button variant="outline" onClick={() => setShowForm(true)}>
                Update Credentials
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-gray-50 p-4 rounded-lg">
            <div>
              <Label className="text-sm font-medium text-gray-700">Access Key ID</Label>
              <div className="flex items-center space-x-2 mt-1">
                <Input
                  type={showSecrets ? 'text' : 'password'}
                  value={config.accessKeyId}
                  readOnly
                  className="bg-white"
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
              <Label className="text-sm font-medium text-gray-700">Region</Label>
              <Input
                value={getRegionLabel(config.region)}
                readOnly
                className="bg-white mt-1"
              />
            </div>
            {config.updatedAt && (
              <div>
                <Label className="text-sm font-medium text-gray-700">Last Updated</Label>
                <Input
                  value={new Date(config.updatedAt).toLocaleDateString()}
                  readOnly
                  className="bg-white mt-1"
                />
              </div>
            )}
          </div>

          {testResult && (
            <div className={`p-4 rounded-lg border ${
              testResult.status === 'error' 
                ? 'bg-red-50 border-red-200' 
                : testResult.status === 'partial' || testResult.permissionIssue
                  ? 'bg-yellow-50 border-yellow-200' 
                  : 'bg-green-50 border-green-200'
            }`}>
              <h4 className={`text-sm font-medium mb-2 ${
                testResult.status === 'error' 
                  ? 'text-red-900' 
                  : testResult.status === 'partial' || testResult.permissionIssue
                    ? 'text-yellow-900' 
                    : 'text-green-900'
              }`}>
                {testResult.status === 'error' 
                  ? '❌ Connection Failed' 
                  : testResult.status === 'partial' || testResult.permissionIssue
                    ? '⚠️ Credentials Valid, Limited Permissions' 
                    : '✅ Connection Test Successful'
                }
              </h4>
              <div className={`text-sm space-y-1 ${
                testResult.status === 'error' 
                  ? 'text-red-700' 
                  : testResult.status === 'partial' || testResult.permissionIssue
                    ? 'text-yellow-700' 
                    : 'text-green-700'
              }`}>
                {testResult.status === 'error' || testResult.permissionIssue ? (
                  <p>{testResult.message}</p>
                ) : (
                  <>
                    <p>Account ID: {testResult.accountId}</p>
                    <p>Region: {testResult.region}</p>
                    <p>Credential Source: {testResult.credentialSource}</p>
                    <p>S3 Buckets Found: {testResult.bucketCount || 0}</p>
                    {testResult.arn && <p>User/Role: {testResult.arn}</p>}
                  </>
                )}
              </div>
            </div>
          )}

          <div className="flex justify-end">
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
        </div>
      ) : showForm || !config?.configured ? (
        <div className="space-y-4">
          <div>
            <h4 className="text-lg font-medium text-gray-900 mb-2">
              {config?.configured ? 'Update AWS Credentials' : 'Configure AWS Credentials'}
            </h4>
            <p className="text-sm text-gray-600">
              Enter your personal AWS credentials for individual project deployments. These will be encrypted and stored securely.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label htmlFor="accessKeyId">AWS Access Key ID</Label>
              <Input
                id="accessKeyId"
                type="text"
                value={formData.accessKeyId}
                onChange={(e) => setFormData({ ...formData, accessKeyId: e.target.value })}
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
                value={formData.secretAccessKey}
                onChange={(e) => setFormData({ ...formData, secretAccessKey: e.target.value })}
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
                value={formData.region}
                onValueChange={(value) => setFormData({ ...formData, region: value })}
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
                Primary AWS region for your personal projects
              </p>
            </div>

            <div className="flex space-x-2 pt-4">
              <Button
                type="submit"
                disabled={isSubmitting || !formData.accessKeyId || !formData.secretAccessKey}
              >
                {isSubmitting ? 'Saving...' : config?.configured ? 'Update Credentials' : 'Save Credentials'}
              </Button>
              {(showForm && config?.configured) && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setShowForm(false)
                    setFormData({ accessKeyId: '', secretAccessKey: '', region: 'us-east-1' })
                  }}
                >
                  Cancel
                </Button>
              )}
            </div>
          </form>
        </div>
      ) : null}

      {!config?.configured && !showForm && (
        <div className="text-center py-8 border-2 border-dashed border-gray-300 rounded-lg">
          <Key className="h-12 w-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No AWS Configuration</h3>
          <p className="text-gray-600 mb-4">
            Configure your personal AWS credentials to enable deployments for your individual projects.
          </p>
          <Button onClick={() => setShowForm(true)}>
            <Key className="h-4 w-4 mr-2" />
            Configure AWS Credentials
          </Button>
        </div>
      )}

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h4 className="text-sm font-medium text-blue-900 mb-2">Security & Usage Information</h4>
        <ul className="text-sm text-blue-700 space-y-1">
          <li>• Personal AWS credentials are encrypted using AES-256 encryption before storage</li>
          <li>• These credentials are used for your individual projects (not team projects)</li>
          <li>• Team projects will use team credentials when available</li>
          <li>• You can view and manage your own credentials at any time</li>
        </ul>
      </div>
    </div>
  )
}