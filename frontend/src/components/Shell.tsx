"use client";

import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

interface ShellProps {
  projectId: string;
}

interface ExecStatus {
  available: boolean;
  runningCount?: number;
  desiredCount?: number;
  status?: string;
  reason?: string;
}

export default function Shell({ projectId }: ShellProps) {
  const [execStatus, setExecStatus] = useState<ExecStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isConnecting, setIsConnecting] = useState(false);
  const [terminalOutput, setTerminalOutput] = useState<string[]>([]);
  const [currentInput, setCurrentInput] = useState("");
  const [sessionActive, setSessionActive] = useState(false);
  const terminalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    checkExecAvailability();
    // Refresh status every 30 seconds
    const interval = setInterval(checkExecAvailability, 30000);
    return () => clearInterval(interval);
  }, [projectId]);

  useEffect(() => {
    // Auto-scroll terminal to bottom when new output is added
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [terminalOutput]);

  const checkExecAvailability = async () => {
    try {
      const response = await fetch(`/api/projects/${projectId}/exec`);
      if (response.ok) {
        const data = await response.json();
        setExecStatus(data);
      } else {
        const errorData = await response.json();
        setError(errorData.error || "Failed to check exec availability");
      }
    } catch (err) {
      setError("Failed to check exec availability");
    } finally {
      setLoading(false);
    }
  };

  const startShellSession = async () => {
    if (!execStatus?.available) return;

    setIsConnecting(true);
    setError("");

    try {
      const response = await fetch(`/api/projects/${projectId}/exec`, {
        method: "POST",
      });

      if (response.ok) {
        const sessionData = await response.json();
        setSessionActive(true);
        setTerminalOutput([
          "🚀 Connected to container shell!",
          `Container: ${sessionData.containerName}`,
          `Task: ${sessionData.taskArn.split("/").pop()}`,
          "─".repeat(60),
          "Welcome to your application container shell.",
          "Type commands and press Enter to execute.",
          "─".repeat(60),
          "",
        ]);

        // For now, this is a mock terminal since AWS Session Manager requires WebSocket
        // In a full implementation, you'd connect to the Session Manager stream
        setTerminalOutput((prev) => [...prev, "$ "]);
      } else {
        const errorData = await response.json();
        setError(errorData.error || "Failed to start shell session");
      }
    } catch (err) {
      setError("Failed to start shell session");
    } finally {
      setIsConnecting(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && sessionActive) {
      e.preventDefault();
      executeCommand(currentInput);
      setCurrentInput("");
    }
  };

  const executeCommand = async (command: string) => {
    if (!command.trim()) return;

    // Add command to output
    setTerminalOutput((prev) => [...prev.slice(0, -1), `$ ${command}`, ""]);

    // Mock command execution for demonstration
    // In a real implementation, this would send commands through the Session Manager WebSocket
    const mockResponse = getMockCommandResponse(command);

    setTimeout(() => {
      setTerminalOutput((prev) => [
        ...prev.slice(0, -1),
        ...mockResponse,
        "$ ",
      ]);
    }, 300);
  };

  const getMockCommandResponse = (command: string): string[] => {
    const cmd = command.trim().toLowerCase();

    if (cmd === "ls" || cmd === "ls -la") {
      return [
        "total 48",
        "drwxr-xr-x 1 root root  4096 Dec 25 12:00 .",
        "drwxr-xr-x 1 root root  4096 Dec 25 12:00 ..",
        "-rw-r--r-- 1 root root   220 Dec 25 12:00 .bashrc",
        "-rw-r--r-- 1 root root   807 Dec 25 12:00 .profile",
        "drwxr-xr-x 6 root root  4096 Dec 25 12:00 app",
        "-rw-r--r-- 1 root root  1024 Dec 25 12:00 package.json",
        "drwxr-xr-x 2 root root  4096 Dec 25 12:00 node_modules",
      ];
    } else if (cmd === "pwd") {
      return ["/app"];
    } else if (cmd.startsWith("cat ")) {
      return [`cat: ${cmd.split(" ")[1]}: Permission denied or file not found`];
    } else if (cmd === "whoami") {
      return ["root"];
    } else if (cmd === "ps aux" || cmd === "ps") {
      return [
        "USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND",
        "root         1  0.1  0.5  12345  6789 ?        Ss   12:00   0:01 node index.js",
        "root        42  0.0  0.1   4567   890 pts/0    R+   12:30   0:00 ps aux",
      ];
    } else if (cmd === "help" || cmd === "--help") {
      return [
        "Available commands:",
        "  ls, ls -la    - List files",
        "  pwd           - Show current directory",
        "  whoami        - Show current user",
        "  ps, ps aux    - Show running processes",
        "  cat <file>    - Show file contents",
        "  exit          - Close shell session",
        "",
        "Note: This is a container shell with limited permissions.",
      ];
    } else if (cmd === "exit") {
      setSessionActive(false);
      return ['Session terminated. Click "Start Shell Session" to reconnect.'];
    } else {
      return [`bash: ${command}: command not found`];
    }
  };

  const disconnectSession = () => {
    setSessionActive(false);
    setTerminalOutput([]);
    setCurrentInput("");
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900 mb-4">
          Container Shell Access
        </h2>
        <p className="text-gray-600 mb-4">
          Access a shell inside your running container to debug, inspect files,
          or run commands.
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg
                className="h-5 w-5 text-red-400"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">Error</h3>
              <p className="text-sm text-red-700 mt-1">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Shell Terminal */}
      {execStatus?.available && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-medium text-gray-900">Interactive Shell</h3>
            <div className="flex space-x-2">
              {!sessionActive ? (
                <Button onClick={startShellSession} disabled={isConnecting}>
                  {isConnecting ? "Connecting..." : "Start Shell Session"}
                </Button>
              ) : (
                <Button onClick={disconnectSession} variant="destructive">
                  Disconnect
                </Button>
              )}
            </div>
          </div>

          {sessionActive && (
            <>
              <div
                ref={terminalRef}
                className="bg-gray-900 text-green-400 p-4 rounded-lg overflow-auto h-96 font-mono text-sm"
              >
                {terminalOutput.map((line, index) => (
                  <div key={index} className="whitespace-pre-wrap">
                    {line}
                    {index === terminalOutput.length - 1 && sessionActive && (
                      <input
                        type="text"
                        value={currentInput}
                        onChange={(e) => setCurrentInput(e.target.value)}
                        onKeyPress={handleKeyPress}
                        className="bg-transparent border-none outline-none text-green-400 font-mono"
                        autoFocus
                        style={{
                          width: `${Math.max(currentInput.length + 1, 1)}ch`,
                        }}
                      />
                    )}
                  </div>
                ))}
              </div>
              <p className="text-sm text-gray-500 mt-2">
                💡 Type "help" for available commands or "exit" to close the
                session.
              </p>
            </>
          )}

          {!sessionActive && terminalOutput.length === 0 && (
            <div className="p-8 rounded-lg text-center">
              <svg
                className="mx-auto h-12 w-12 text-gray-400 mb-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v14a2 2 0 002 2z"
                />
              </svg>
              <p className="text-gray-500">
                Click "Start Shell Session" to connect to your container.
              </p>
            </div>
          )}
        </div>
      )}

      {!execStatus?.available && (
        <div className="p-8 rounded-lg text-center">
          <svg
            className="mx-auto h-12 w-12 text-gray-400 mb-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
            />
          </svg>
          <p className="text-gray-500 mb-2">Shell access is not available</p>
          <p className="text-sm text-gray-400">
            Your application needs to have running containers to access the
            shell.
          </p>
        </div>
      )}
    </div>
  );
}
