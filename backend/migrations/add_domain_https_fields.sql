-- Add domain and HTTPS fields to environments table
ALTER TABLE environments 
ADD COLUMN IF NOT EXISTS certificate_arn VARCHAR(255),
ADD COLUMN IF NOT EXISTS enable_https BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS auto_provision_certificate BOOLEAN DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS use_route53_validation BOOLEAN DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS custom_domain VARCHAR(255);

-- Update existing environments to have sensible defaults
UPDATE environments 
SET enable_https = FALSE 
WHERE enable_https IS NULL;

UPDATE environments 
SET auto_provision_certificate = TRUE 
WHERE auto_provision_certificate IS NULL;

UPDATE environments 
SET use_route53_validation = FALSE 
WHERE use_route53_validation IS NULL;

-- Migrate existing custom domains: if domain doesn't contain 'elb.amazonaws.com', 
-- it's a custom domain and should be moved to custom_domain field
UPDATE environments 
SET custom_domain = domain,
    domain = NULL
WHERE domain IS NOT NULL 
AND domain NOT LIKE '%.elb.amazonaws.com';