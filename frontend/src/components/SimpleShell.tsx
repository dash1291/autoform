'use client'

import { useState, useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { apiClient } from '@/lib/api'

interface SimpleShellProps {
  projectId: string
  isActive?: boolean
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

export default function SimpleShell({ projectId, isActive = false }: SimpleShellProps) {
  const [execStatus, setExecStatus] = useState<ExecStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)
  const [shellCommand, setShellCommand] = useState<ShellCommand | null>(null)

  useEffect(() => {
    checkExecAvailability()
    // Refresh status every 30 seconds
    const interval = setInterval(checkExecAvailability, 30000)
    return () => clearInterval(interval)
  }, [projectId])

  // Auto-generate shell command when tab becomes active and exec is available
  useEffect(() => {
    if (isActive && execStatus?.available && !shellCommand && !isGenerating) {
      generateShellCommand()
    }
  }, [isActive, execStatus?.available])

  const checkExecAvailability = async () => {
    try {
      const data = await apiClient.checkExecAvailability(projectId)
      setExecStatus(data)
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
      const data = await apiClient.checkExecAvailability(projectId)
      
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
--region "${data.region || 'us-east-1'}" \\
--cluster "${data.clusterArn}" \\
--task "${data.taskArn}" \\
--container "${data.containerName}" \\
--interactive \\
--command "/bin/bash"`

      // Set the shell command
      setShellCommand({
        command: shellCommand,
        timestamp: new Date()
      })
    } catch (err) {
      setError('Failed to generate shell command')
    } finally {
      setIsGenerating(false)
    }
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

      {/* Command Execution Interface */}
      {execStatus?.available && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          {shellCommand ? (
            <>
              <div className="mb-2">
                <span className="text-sm font-medium text-gray-700">
                  Shell Access Command
                </span>
              </div>
              <div className="bg-gray-900 text-green-400 p-3 rounded font-mono text-sm overflow-x-auto">
                <pre className="whitespace-pre-wrap">{shellCommand.command}</pre>
              </div>
              <div className="mt-2 flex space-x-2">
                <Button
                  onClick={() => navigator.clipboard.writeText(shellCommand.command)}
                  variant="outline"
                  size="sm"
                  className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded hover:bg-blue-200"
                >
                  Copy Command
                </Button>
                <span className="text-xs text-gray-500">
                  Run this command in your terminal (requires AWS CLI configured)
                </span>
              </div>
            </>
          ) : isGenerating ? (
            <div className="bg-gray-50 p-8 rounded-lg text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-500 mb-2">Generating shell command...</p>
              <p className="text-sm text-gray-400">
                Please wait while we prepare your container shell access.
              </p>
            </div>
          ) : (
            <div className="bg-gray-50 p-8 rounded-lg text-center">
              <svg className="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 002 2v14a2 2 0 002 2z" />
              </svg>
              <p className="text-gray-500 mb-2">Shell command will appear here</p>
              <p className="text-sm text-gray-400">
                A shell access command is automatically generated when this tab opens.
              </p>
            </div>
          )}
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