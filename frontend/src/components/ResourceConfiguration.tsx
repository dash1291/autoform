"use client";

import { useState, useEffect } from "react";
import { Project } from "@/types";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { apiClient } from "@/lib/api";

interface ResourceConfigurationProps {
  projectId: string;
  environmentId?: string;
  project: Project;
  onUpdate: () => void;
}

export default function ResourceConfiguration({
  projectId,
  environmentId,
  project,
  onUpdate,
}: ResourceConfigurationProps) {
  // If environmentId is provided, we need to load and configure that environment's resources
  const [environment, setEnvironment] = useState<any>(null);
  const [loadingEnv, setLoadingEnv] = useState(false);

  useEffect(() => {
    if (environmentId) {
      fetchEnvironment();
    }
  }, [environmentId]);

  const fetchEnvironment = async () => {
    if (!environmentId) return;
    setLoadingEnv(true);
    try {
      const envData = await apiClient.getEnvironment(environmentId);
      setEnvironment(envData);
      setFormData({
        cpu: envData.cpu || 256,
        memory: envData.memory || 512,
        diskSize: envData.diskSize || 21,
      });
    } catch (error) {
      console.error("Failed to fetch environment:", error);
    } finally {
      setLoadingEnv(false);
    }
  };

  const [formData, setFormData] = useState({
    cpu: project.cpu || 256,
    memory: project.memory || 512,
    diskSize: project.diskSize || 21,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setSuccess("");

    try {
      if (environmentId) {
        // Update environment resources
        await apiClient.updateEnvironment(environmentId, {
          cpu: formData.cpu,
          memory: formData.memory,
          diskSize: formData.diskSize,
        });
        setSuccess("Environment resource configuration updated successfully!");
        await fetchEnvironment(); // Refresh environment data
      } else {
        // Update project resources (legacy)
        await apiClient.updateProject(projectId, formData);
        setSuccess("Resource configuration updated successfully!");
      }
      onUpdate();
    } catch (err: any) {
      setError(err.message || "Failed to update resource configuration");
    } finally {
      setLoading(false);
    }
  };

  // Check if form data has changed from original values
  const originalData = environmentId ? environment : project;
  const hasChanges =
    originalData &&
    (formData.cpu !== (originalData.cpu || 256) ||
      formData.memory !== (originalData.memory || 512) ||
      formData.diskSize !== (originalData.diskSize || 21));

  const isDeploying = false; // Status is now at environment level

  return (
    <Card>
      <CardHeader>
        <CardTitle>Resource Configuration</CardTitle>
        <CardDescription>
          {environmentId
            ? "Configure CPU, memory, and storage resources for this environment"
            : "Configure CPU, memory, and storage resources for your deployment"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label htmlFor="cpu">CPU (units)</Label>
              <Select
                value={formData.cpu.toString()}
                onValueChange={(value) =>
                  setFormData({ ...formData, cpu: parseInt(value) })
                }
                disabled={isDeploying}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="256">256 (0.25 vCPU)</SelectItem>
                  <SelectItem value="512">512 (0.5 vCPU)</SelectItem>
                  <SelectItem value="1024">1024 (1 vCPU)</SelectItem>
                  <SelectItem value="2048">2048 (2 vCPU)</SelectItem>
                  <SelectItem value="4096">4096 (4 vCPU)</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                AWS Fargate CPU allocation
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="memory">Memory (MB)</Label>
              <Select
                value={formData.memory.toString()}
                onValueChange={(value) =>
                  setFormData({ ...formData, memory: parseInt(value) })
                }
                disabled={isDeploying}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="512">512 MB</SelectItem>
                  <SelectItem value="1024">1 GB</SelectItem>
                  <SelectItem value="2048">2 GB</SelectItem>
                  <SelectItem value="4096">4 GB</SelectItem>
                  <SelectItem value="8192">8 GB</SelectItem>
                  <SelectItem value="16384">16 GB</SelectItem>
                  <SelectItem value="30720">30 GB</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Container memory limit
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="diskSize">Disk Size (GB)</Label>
              <Input
                id="diskSize"
                type="number"
                min="21"
                max="200"
                value={formData.diskSize}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    diskSize: parseInt(e.target.value) || 21,
                  })
                }
                disabled={isDeploying}
              />
              <p className="text-xs text-muted-foreground">
                Ephemeral storage (21-200 GB)
              </p>
            </div>
          </div>

          {error && (
            <div className="bg-destructive/15 border border-destructive/20 rounded-lg p-4">
              <p className="text-destructive">{error}</p>
            </div>
          )}

          {success && (
            <div className="bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800/30 rounded-lg p-4">
              <p className="text-green-800 dark:text-green-400">{success}</p>
            </div>
          )}

          {isDeploying && (
            <div className="bg-yellow-50 dark:bg-yellow-950/30 border border-yellow-200 dark:border-yellow-800/30 rounded-lg p-4">
              <p className="text-yellow-800 dark:text-yellow-400">
                Cannot modify resource configuration while deployment is in
                progress.
              </p>
            </div>
          )}

          <div className="flex space-x-4">
            <Button
              type="submit"
              size="sm"
              disabled={loading || isDeploying || !hasChanges}
            >
              {loading ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
