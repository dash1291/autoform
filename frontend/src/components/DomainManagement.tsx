"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { apiClient } from "@/lib/api";
import { Environment } from "@/types";
import {
  Globe,
  Lock,
  ExternalLink,
  AlertCircle,
  CheckCircle,
  Copy,
  Server,
  RefreshCw,
} from "lucide-react";

interface DomainManagementProps {
  projectId: string;
  teamId?: string;
}

export default function DomainManagement({
  projectId,
  teamId,
}: DomainManagementProps) {
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [selectedEnvironmentId, setSelectedEnvironmentId] =
    useState<string>("");
  const [selectedEnvironment, setSelectedEnvironment] =
    useState<Environment | null>(null);
  const [loading, setLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [certificateInfo, setCertificateInfo] = useState<any>(null);
  const [certificateStatus, setCertificateStatus] = useState<any>(null);
  const [isRefreshingStatus, setIsRefreshingStatus] = useState(false);

  // Form state
  const [domainData, setDomainData] = useState({
    domain: "",
    autoProvisionCertificate: true,
    useRoute53Validation: false,
  });

  useEffect(() => {
    fetchEnvironments();
  }, [projectId]);

  useEffect(() => {
    if (selectedEnvironmentId) {
      const env = environments.find((e) => e.id === selectedEnvironmentId);
      setSelectedEnvironment(env || null);
      if (env) {
        setDomainData({
          domain: env.domain || "",
          autoProvisionCertificate: env.autoProvisionCertificate !== false,
          useRoute53Validation: env.useRoute53Validation === true,
        });

        // Fetch certificate status if custom domain exists
        if (env.domain) {
          fetchCertificateStatus(env.id);
        }
      }
    } else {
      setSelectedEnvironment(null);
      setDomainData({
        domain: "",
        autoProvisionCertificate: true,
        useRoute53Validation: false,
      });
    }
  }, [selectedEnvironmentId, environments]);

  const fetchEnvironments = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getProjectEnvironments(projectId);
      setEnvironments(data);

      // Auto-select first environment (regardless of status)
      if (data.length > 0 && !selectedEnvironmentId) {
        setSelectedEnvironmentId(data[0].id);
      }
    } catch (error: any) {
      setError("Failed to load environments");
    } finally {
      setLoading(false);
    }
  };

  const fetchCertificateStatus = async (
    environmentId: string,
    showLoading = false
  ) => {
    if (showLoading) setIsRefreshingStatus(true);
    try {
      const status = await apiClient.getCertificateStatus(environmentId);
      console.log("Certificate status response:", status);
      setCertificateStatus(status);
    } catch (error) {
      console.error("Certificate status error:", error);
      setCertificateStatus({
        status: "error",
        message: "Failed to check certificate status",
      });
    } finally {
      if (showLoading) setIsRefreshingStatus(false);
    }
  };

  const handleRefreshStatus = () => {
    if (selectedEnvironment) {
      fetchCertificateStatus(selectedEnvironment.id, true);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedEnvironment) return;

    setIsSubmitting(true);
    setError("");
    setSuccess("");
    setCertificateInfo(null);

    try {
      const updateData = {
        domain: domainData.domain || null,
        autoProvisionCertificate: domainData.autoProvisionCertificate,
        useRoute53Validation: false, // Always false since we don't support Route53 validation yet
      };

      const result = await apiClient.updateEnvironment(
        selectedEnvironment.id,
        updateData
      );

      setSuccess("Domain configuration updated successfully!");

      // Refresh environments and certificate status
      await fetchEnvironments();
      if (domainData.domain) {
        await fetchCertificateStatus(selectedEnvironment.id);
      }
    } catch (error: any) {
      setError(error.message || "Failed to configure domain");
    } finally {
      setIsSubmitting(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setSuccess("Copied to clipboard!");
  };

  // Show all environments, not just deployed ones
  const deployedEnvironments = environments;

  if (loading) {
    return (
      <div className="text-center py-8">
        <p className="text-muted-foreground">Loading environments...</p>
      </div>
    );
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

      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-medium text-foreground">
              Domain Management
            </h3>
            <p className="text-sm text-muted-foreground">
              Configure custom domains for your deployed environments
            </p>
          </div>
          <div className="min-w-[200px]">
            {deployedEnvironments.length === 0 ? (
              <div className="text-sm text-muted-foreground">
                No deployed environments
              </div>
            ) : (
              <Select
                value={selectedEnvironmentId}
                onValueChange={setSelectedEnvironmentId}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select environment" />
                </SelectTrigger>
                <SelectContent>
                  {deployedEnvironments.map((env) => (
                    <SelectItem key={env.id} value={env.id}>
                      {env.name} ({env.awsConfig?.region})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
        </div>

        {deployedEnvironments.length === 0 ? (
          <div className="text-center py-12 rounded-lg">
            <Server className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-medium">No Deployed Environments</h3>
            <p className="text-muted-foreground text-sm mt-2">
              Deploy an environment first before configuring custom domains
            </p>
          </div>
        ) : !selectedEnvironmentId ? (
          <div className="text-center py-12 bg-muted rounded-lg">
            <p className="text-muted-foreground">
              Select an environment to configure its domain.
            </p>
          </div>
        ) : (
          selectedEnvironment && <></>
        )}
      </div>

      {selectedEnvironment && (
        <div>
          <div>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <Label>Custom Domain</Label>
                <Input
                  type="text"
                  value={domainData.domain}
                  onChange={(e) =>
                    setDomainData({ ...domainData, domain: e.target.value })
                  }
                  placeholder="e.g., app.example.com"
                  className="mt-1"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Leave empty to use only the load balancer URL
                </p>
              </div>
              <div className="flex justify-end space-x-2">
                <Button size="sm" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? "Updating..." : "Update Domain"}
                </Button>
              </div>
              {certificateStatus && (
                <>
                  <div className="flex items-center">
                    <div className="flex items-center space-x-2">
                      <span className="text-sm font-medium">
                        Domain Validation Status:{" "}
                      </span>
                    </div>
                    <span
                      className={`text-xs px-2 py-1 ml-3 rounded-full ${
                        certificateStatus.status === "ready"
                          ? "bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400"
                          : certificateStatus.status === "pending_validation"
                          ? "bg-muted text-muted-foreground"
                          : certificateStatus.status === "failed" ||
                            certificateStatus.status === "error"
                          ? "bg-destructive/10 text-destructive"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {certificateStatus.status === "ready"
                        ? "Done"
                        : certificateStatus.status === "pending_validation"
                        ? "Pending"
                        : certificateStatus.status === "not_requested"
                        ? "Pending"
                        : certificateStatus.status === "failed"
                        ? "Failed"
                        : certificateStatus.status === "error"
                        ? "Error"
                        : "Unknown"}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleRefreshStatus}
                      disabled={isRefreshingStatus}
                      className="h-7 ml-1 w-7 p-0"
                    >
                      <RefreshCw
                        className={`h-3 w-3 ${
                          isRefreshingStatus ? "animate-spin" : ""
                        }`}
                      />
                    </Button>
                  </div>
                  <p className="text-xs mt-0 text-muted-foreground">
                    {certificateStatus.message}
                  </p>
                </>
              )}
              {((certificateInfo && certificateInfo.validationRequired) ||
                (certificateStatus &&
                  certificateStatus.status === "pending_validation")) && (
                <div className="mt-4 border-primary/20 bg-primary/5">
                  <div className="space-y-4">
                    {certificateInfo?.validationRequired === "manual" ||
                    certificateStatus?.validationRequired === "manual" ? (
                      <>
                        <p className="text-sm text-muted-foreground">
                          Please add the following DNS records to validate your
                          domain ownership:
                        </p>

                        {(
                          certificateInfo?.validationRecords ||
                          certificateStatus?.validationRecords ||
                          []
                        ).map((record: any, index: number) => (
                          <Card key={index} className="bg-background">
                            <CardContent className="p-3">
                              <div className="flex items-center justify-between mb-2">
                                <p className="text-sm font-medium text-foreground">
                                  Validation Record {index + 1}
                                </p>
                                {record.Domains &&
                                  record.Domains.length > 0 && (
                                    <span className="text-xs text-muted-foreground">
                                      for {record.Domains.join(", ")}
                                    </span>
                                  )}
                              </div>
                              <div className="space-y-2 text-xs">
                                <div>
                                  <div className="font-medium text-foreground mb-1">
                                    Type:
                                  </div>
                                  <code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono text-foreground block">
                                    {record.Type || "CNAME"}
                                  </code>
                                </div>
                                <div>
                                  <div className="font-medium text-foreground mb-1">
                                    Name:
                                  </div>
                                  <code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono text-foreground block break-all">
                                    {record.Name}
                                  </code>
                                </div>
                                <div>
                                  <div className="font-medium text-foreground mb-1">
                                    Value:
                                  </div>
                                  <code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono text-foreground block break-all">
                                    {record.Value}
                                  </code>
                                </div>
                              </div>
                            </CardContent>
                          </Card>
                        ))}

                        <div className="text-sm text-muted-foreground space-y-1">
                          <p>
                            • Validation typically completes within
                            15 minutes after DNS records have been set
                          </p>
                          <p>• You can check status by refreshing this page</p>
                        </div>
                      </>
                    ) : (
                      <>
                        <p className="text-sm text-muted-foreground">
                          Route53 validation SSL Certificate Validation Required
                          on is in progress. The certificate will be
                          automatically validated.
                        </p>

                        <div className="text-sm text-muted-foreground space-y-1">
                          <p>
                            • Route53 DNS validation is handling the
                            verification automatically
                          </p>
                          <p>
                            • Certificate validation typically completes within
                            15 minutes
                          </p>
                          <p>• No manual action required</p>
                        </div>

                        {certificateInfo?.certificateStatus && (
                          <div className="text-xs text-muted-foreground">
                            Current status: {certificateInfo.certificateStatus}
                          </div>
                        )}Please add the following DNS records to validate your domain ownership:


                      </>
                    )}
                  </div>
                </div>
              )}
              {certificateStatus && certificateStatus.status === "ready" && (
                <Card className="">
                  <CardContent className="p-4">
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">
                          Load Balancer DNS:
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Create a CNAME record pointing your domain to this load
                        balancer DNS name to finish setting up your domain
                      </p>
                    </div>
                    <div className="flex items-center space-x-2">
                          <code className="bg-muted mt-2 px-1.5 py-0.5 rounded text-sm font-mono text-foreground block break-all">
                            {selectedEnvironment.albDns || "Not available"}
                          </code>
                        </div>
                  </CardContent>
                </Card>
              )}
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
