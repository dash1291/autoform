'use client'

import { useState, useEffect, useRef } from 'react'

interface SimpleShellProps {
  projectId: string
}

interface ExecStatus {
  available: boolean
  runningCount?: number
  desiredCount?: number
  status?: string
  reason?: string
}

interface ShellCommand {
  command: string
  timestamp: Date
}

export default function SimpleShell({ projectId }: SimpleShellProps) {
  const [execStatus, setExecStatus] = useState<ExecStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)
  const [shellCommands, setShellCommands] = useState<ShellCommand[]>([])
  const outputRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    checkExecAvailability()
    // Refresh status every 30 seconds
    const interval = setInterval(checkExecAvailability, 30000)
    return () => clearInterval(interval)
  }, [projectId])

  useEffect(() => {
    // Auto-scroll output to bottom when new commands are added
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight
    }
  }, [shellCommands])

  const checkExecAvailability = async () => {
    try {
      const response = await fetch(`/api/projects/${projectId}/exec`)
      if (response.ok) {
        const data = await response.json()
        setExecStatus(data)
      } else {
        const errorData = await response.json()
        setError(errorData.error || 'Failed to check exec availability')
      }
    } catch (err) {
      setError('Failed to check exec availability')
    } finally {
      setLoading(false)
    }
  }

  const generateShellCommand = async () => {
    if (!execStatus?.available) return

    setIsGenerating(true)
    setError('')

    try {
      const response = await fetch(`/api/projects/${projectId}/exec`)
      
      if (response.ok) {
        const data = await response.json()
        
        if (!data.available) {
          setError('Shell access is not available - no running containers found')
          return
        }

        if (!data.clusterArn || !data.taskArn || !data.containerName) {
          setError('Unable to get container information - missing cluster, task, or container details')
          return
        }
        
        // Generate the AWS CLI command for shell access
        const shellCommand = `aws ecs execute-command \\
  --cluster "${data.clusterArn}" \\
  --task "${data.taskArn}" \\
  --container "${data.containerName}" \\
  --interactive \\
  --command "/bin/bash"`

        // Add the command to history
        setShellCommands(prev => [...prev, {
          command: shellCommand,
          timestamp: new Date()
        }])
      } else {
        const errorData = await response.json()
        setError(errorData.error || 'Failed to get container information')
      }
    } catch (err) {
      setError('Failed to generate shell command')
    } finally {
      setIsGenerating(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      generateShellCommand()
    }
  }

  const clearHistory = () => {
    setShellCommands([])
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Container Shell Access</h2>
        <p className="text-gray-600 mb-4">
          Get the AWS CLI command to access a shell in your running container.
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">Error</h3>
              <p className="text-sm text-red-700 mt-1">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Status Card */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h3 className="font-medium text-gray-900 mb-2">Service Status</h3>
        {execStatus ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">Shell Access:</span>
              <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                execStatus.available 
                  ? 'bg-green-100 text-green-800' 
                  : 'bg-red-100 text-red-800'
              }`}>
                {execStatus.available ? 'Available' : 'Unavailable'}
              </span>
            </div>
            {execStatus.runningCount !== undefined && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Running Tasks:</span>
                <span className="text-sm text-gray-900">
                  {execStatus.runningCount}/{execStatus.desiredCount}
                </span>
              </div>
            )}
            {execStatus.status && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Service Status:</span>
                <span className="text-sm text-gray-900">{execStatus.status}</span>
              </div>
            )}
            {!execStatus.available && execStatus.reason && (
              <p className="text-sm text-red-600 mt-2">{execStatus.reason}</p>
            )}
          </div>
        ) : (
          <p className="text-sm text-gray-500">Loading status...</p>
        )}
      </div>

      {/* Command Execution Interface */}
      {execStatus?.available && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-medium text-gray-900">Generate Shell Command</h3>
            {shellCommands.length > 0 && (
              <button
                onClick={clearHistory}
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                Clear History
              </button>
            )}
          </div>

          {/* Generate Button */}
          <div className="mb-4">
            <button
              onClick={generateShellCommand}
              disabled={isGenerating}
              className="bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors w-full"
            >
              {isGenerating ? 'Generating Command...' : 'Generate Shell Access Command'}
            </button>
            <p className="text-xs text-gray-500 mt-2">
              Generates an AWS CLI command you can run in your terminal to access the container shell
            </p>
          </div>

          {/* Generated Commands */}
          {shellCommands.length > 0 ? (
            <div 
              ref={outputRef}
              className="bg-gray-50 border border-gray-200 rounded-lg p-4 max-h-96 overflow-y-auto"
            >
              <h4 className="text-sm font-medium text-gray-700 mb-3">Generated Commands</h4>
              <div className="space-y-4">
                {shellCommands.map((entry, index) => (
                  <div key={index} className="bg-white border border-gray-200 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-gray-700">
                        Shell Access Command #{shellCommands.length - index}
                      </span>
                      <span className="text-xs text-gray-500">
                        {entry.timestamp.toLocaleTimeString()}
                      </span>
                    </div>
                    <div className="bg-gray-900 text-green-400 p-3 rounded font-mono text-sm overflow-x-auto">
                      <pre className="whitespace-pre-wrap">{entry.command}</pre>
                    </div>
                    <div className="mt-2 flex space-x-2">
                      <button
                        onClick={() => navigator.clipboard.writeText(entry.command)}
                        className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded hover:bg-blue-200 transition-colors"
                      >
                        Copy Command
                      </button>
                      <span className="text-xs text-gray-500">
                        Run this command in your terminal (requires AWS CLI configured)
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="bg-gray-50 p-8 rounded-lg text-center">
              <svg className="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 002 2v14a2 2 0 002 2z" />
              </svg>
              <p className="text-gray-500 mb-2">No commands generated yet</p>
              <p className="text-sm text-gray-400">
                Click the button above to generate an AWS CLI command for shell access.
              </p>
            </div>
          )}

          <div className="mt-4 text-sm text-gray-500">
            <p className="mb-1">💡 <strong>How to Use:</strong></p>
            <ul className="list-disc list-inside space-y-1 text-xs">
              <li>Click "Generate Shell Access Command" to get the AWS CLI command</li>
              <li>Copy the generated command and run it in your terminal</li>
              <li>Requires AWS CLI installed and configured with proper credentials</li>
              <li>The command will give you an interactive bash shell in your container</li>
              <li>You can run any commands like <code>ls</code>, <code>ps</code>, <code>cat</code>, etc.</li>
            </ul>
          </div>
        </div>
      )}

      {!execStatus?.available && (
        <div className="bg-gray-50 p-8 rounded-lg text-center">
          <svg className="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
          <p className="text-gray-500 mb-2">Shell access is not available</p>
          <p className="text-sm text-gray-400">
            Your application needs to have running containers to generate shell access commands.
          </p>
        </div>
      )}
    </div>
  )
}