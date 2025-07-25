import React from 'react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Copy, ExternalLink, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface ValidationRecord {
  Name: string
  Value: string
  Type: string
}

interface DomainValidationInstructionsProps {
  domain: string
  validationRecords: ValidationRecord[]
  loadBalancerDns: string
  certificateStatus: 'PENDING_VALIDATION' | 'ISSUED' | 'FAILED'
}

export default function DomainValidationInstructions({ 
  domain, 
  validationRecords, 
  loadBalancerDns,
  certificateStatus 
}: DomainValidationInstructionsProps) {
  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      // You could add a toast notification here
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const getDnsProviderInstructions = () => {
    const providers = [
      { name: 'GoDaddy', url: 'https://dcc.godaddy.com/manage/dns' },
      { name: 'Namecheap', url: 'https://www.namecheap.com/domains/domaincontrolpanel' },
      { name: 'Cloudflare', url: 'https://dash.cloudflare.com' },
    ]
    
    return providers
  }

  return (
    <div className="space-y-6">
      {certificateStatus === 'PENDING_VALIDATION' && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Your SSL certificate is pending validation. Please add the following DNS records to validate domain ownership.
          </AlertDescription>
        </Alert>
      )}

      <div className="space-y-4">
        <h3 className="text-lg font-semibold">Step 1: Certificate Validation Records</h3>
        <p className="text-sm text-muted-foreground">
          Add these CNAME records to validate your domain ownership with AWS Certificate Manager:
        </p>
        
        {validationRecords.map((record, index) => (
          <div key={index} className="bg-secondary p-4 rounded-lg space-y-2">
            <div className="flex justify-between items-start">
              <div className="space-y-1 flex-1">
                <p className="text-sm font-medium">Record {index + 1}</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-muted-foreground">Name/Host</p>
                    <code className="text-sm bg-background px-2 py-1 rounded">{record.Name}</code>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Value/Points to</p>
                    <code className="text-sm bg-background px-2 py-1 rounded break-all">{record.Value}</code>
                  </div>
                </div>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => copyToClipboard(`${record.Name} -> ${record.Value}`)}
              >
                <Copy className="h-4 w-4" />
              </Button>
            </div>
          </div>
        ))}
      </div>

      <div className="space-y-4">
        <h3 className="text-lg font-semibold">Step 2: Point Your Domain to Load Balancer</h3>
        <p className="text-sm text-muted-foreground">
          After validation, add this CNAME record to point your domain to the AWS load balancer:
        </p>
        
        <div className="bg-secondary p-4 rounded-lg">
          <div className="flex justify-between items-start">
            <div className="space-y-1 flex-1">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-muted-foreground">Name/Host</p>
                  <code className="text-sm bg-background px-2 py-1 rounded">{domain}</code>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Value/Points to</p>
                  <code className="text-sm bg-background px-2 py-1 rounded break-all">{loadBalancerDns}</code>
                </div>
              </div>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => copyToClipboard(`${domain} -> ${loadBalancerDns}`)}
            >
              <Copy className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      <div className="space-y-4">
        <h3 className="text-lg font-semibold">DNS Provider Instructions</h3>
        <p className="text-sm text-muted-foreground">
          Select your DNS provider for specific instructions:
        </p>
        
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
          {getDnsProviderInstructions().map((provider) => (
            <Button
              key={provider.name}
              variant="outline"
              size="sm"
              onClick={() => window.open(provider.url, '_blank')}
            >
              {provider.name}
              <ExternalLink className="h-3 w-3 ml-1" />
            </Button>
          ))}
        </div>
      </div>

      <Alert>
        <AlertDescription>
          <strong>Note:</strong> DNS changes can take 5-30 minutes to propagate. 
          Certificate validation typically completes within 15 minutes after DNS records are added.
        </AlertDescription>
      </Alert>
    </div>
  )
}