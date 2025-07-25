-- Remove enable_https field as HTTPS should be enabled by default
ALTER TABLE environments 
DROP COLUMN IF EXISTS enable_https;