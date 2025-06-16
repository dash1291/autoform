'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { apiClient } from '@/lib/api'

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
  projectId: string
}

export default function LogsViewer({ projectId }: LogsViewerProps) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [limit] = useState(200) // Fixed limit, no UI control
  const [hoursBack, setHoursBack] = useState(1)

  const fetchLogs = async () => {
    setLoading(true)
    setError(null)
    
    try {
      const data: LogsResponse = await apiClient.getProjectLogs(projectId, limit, hoursBack)
      
      // Debug: Log the timestamps to see what we're getting
      if (data.logs && data.logs.length > 0) {
        console.log('First log timestamp:', data.logs[0].timestamp, 'Date:', new Date(data.logs[0].timestamp))
        console.log('Last log timestamp:', data.logs[data.logs.length - 1].timestamp, 'Date:', new Date(data.logs[data.logs.length - 1].timestamp))
        console.log(`Fetched ${data.logs.length} logs from last ${hoursBack} hour(s)`)
      }
      
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
  }, [projectId, limit, hoursBack])

  useEffect(() => {
    if (!autoRefresh) return

    const interval = setInterval(fetchLogs, 5000) // Refresh every 5 seconds
    return () => clearInterval(interval)
  }, [autoRefresh, projectId, limit, hoursBack])

  const formatLogMessage = (message: string) => {
    // Basic formatting for common log patterns
    if (message.includes('ERROR') || message.includes('error')) {
      return 'text-red-600'
    }
    if (message.includes('WARN') || message.includes('warn')) {
      return 'text-yellow-600'
    }
    if (message.includes('INFO') || message.includes('info')) {
      return 'text-blue-600'
    }
    return 'text-gray-700'
  }

  const formatTimestamp = (timestamp: number) => {
    return new Date(timestamp).toLocaleString()
  }

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between bg-gray-50 p-4 rounded-lg">
        <div className="flex flex-wrap gap-4 items-center">
          <Button
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
            <span className="text-sm text-gray-700">Auto-refresh (5s)</span>
          </label>
          
          <select
            value={hoursBack}
            onChange={(e) => setHoursBack(parseInt(e.target.value))}
            className="border border-gray-300 rounded px-3 py-2 text-sm"
          >
            <option value={1}>Last 1 hour</option>
            <option value={3}>Last 3 hours</option>
            <option value={6}>Last 6 hours</option>
            <option value={12}>Last 12 hours</option>
            <option value={24}>Last 24 hours</option>
          </select>
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
      <div className="bg-black text-green-400 font-mono text-sm rounded-lg overflow-hidden">
        <div className="bg-gray-800 px-4 py-2 text-white text-xs border-b border-gray-700">
          Application Logs
        </div>
        
        <div className="max-h-96 overflow-y-auto">
          {loading && logs.length === 0 ? (
            <div className="p-4 text-center text-gray-400">
              Loading logs...
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