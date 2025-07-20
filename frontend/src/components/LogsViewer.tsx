'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { apiClient } from '@/lib/api'
import { formatLogTime } from '@/lib/dateUtils'
import { Spinner } from '@/components/ui/spinner'

interface LogEntry {
  timestamp: number
  message: string
  logStreamName: string
  formattedTime: string
}

interface LogsResponse {
  logs: LogEntry[]
  logGroupName?: string
  totalStreams?: number
  error?: string
  message?: string
}

interface LogsViewerProps {
  environmentId: string
}

export default function LogsViewer({ environmentId }: LogsViewerProps) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [hoursBack, setHoursBack] = useState(1)
  
  const limit = 1000 // Fixed limit of 1000 logs

  const fetchLogs = async () => {
    setLoading(true)
    setError(null)
    
    try {
      const data = await apiClient.getEnvironmentLogs(environmentId, limit, hoursBack) as LogsResponse
      
      setLogs(data.logs || [])
      
      if (data.message && data.logs.length === 0) {
        setError(data.message)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch logs')
      setLogs([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchLogs()
  }, [environmentId, limit, hoursBack])

  useEffect(() => {
    if (!autoRefresh) return

    const interval = setInterval(fetchLogs, 5000) // Refresh every 5 seconds
    return () => clearInterval(interval)
  }, [autoRefresh, environmentId, limit, hoursBack])

  const formatLogMessage = (message: string) => {
    // Basic formatting for common log patterns
    if (message.includes('ERROR') || message.includes('error')) {
      return 'text-red-400'
    }
    if (message.includes('WARN') || message.includes('warn')) {
      return 'text-yellow-400'
    }
    if (message.includes('INFO') || message.includes('info')) {
      return 'text-blue-400'
    }
    return 'text-gray-300'
  }

  const formatTimestamp = (timestamp: number) => {
    return formatLogTime(timestamp)
  }

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between bg-background p-4 rounded-lg">
        <div className="flex flex-wrap gap-4 items-center">
          <Button
            size="sm"
            onClick={fetchLogs}
            disabled={loading}
          >
            {loading ? 'Loading...' : 'Refresh'}
          </Button>
          
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded"
            />
            <span className="text-sm text-foreground">Auto-refresh (5s)</span>
          </label>
          
          <Select 
            value={hoursBack.toString()} 
            onValueChange={(value) => setHoursBack(parseInt(value))}
          >
            <SelectTrigger className="w-[180px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1">Last 1 hour</SelectItem>
              <SelectItem value="3">Last 3 hours</SelectItem>
              <SelectItem value="6">Last 6 hours</SelectItem>
              <SelectItem value="12">Last 12 hours</SelectItem>
              <SelectItem value="24">Last 24 hours</SelectItem>
            </SelectContent>
          </Select>
        </div>
        
        {logs.length > 0 && (
          <div className="text-sm text-gray-500">
            Showing {logs.length} logs
          </div>
        )}
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {/* Logs Display */}
      <div className="bg-gray-900 text-green-400 font-mono text-sm rounded overflow-hidden">
        <div className="max-h-96 overflow-y-auto">
          {loading && logs.length === 0 ? (
            <div className="p-4 text-center text-gray-400">
              Loading logs 
              <div className="flex items-center justify-center py-8">
                <Spinner color="secondary" />
              </div>
            </div>
          ) : logs.length === 0 ? (
            <div className="p-4 text-center text-gray-400">
              No logs available. Deploy your application to see logs here.
            </div>
          ) : (
            <div className="p-4 space-y-1">
              {logs.map((log, index) => (
                <div key={`${log.timestamp}-${index}`} className="flex flex-col sm:flex-row gap-2">
                  <span className="text-gray-400 text-xs whitespace-nowrap">
                    {formatTimestamp(log.timestamp)}
                  </span>
                  <span className="text-xs text-gray-500 sm:ml-2">
                    [{log.logStreamName?.split('/').pop()}]
                  </span>
                  <span className={`flex-1 break-all ${formatLogMessage(log.message || '')}`}>
                    {log.message?.trim() || '(empty log)'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      
      {logs.length > 0 && (
        <div className="text-xs text-gray-500 text-center">
          Logs are automatically retained for 7 days
        </div>
      )}
    </div>
  )
}