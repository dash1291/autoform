-- Move existing webhook secrets from Project table to Webhook table
-- This migration handles cases where webhookSecret column may or may not exist

-- Check if webhookSecret column exists and migrate data if it does
DO $$
BEGIN
    -- Check if the webhookSecret column exists
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'Project' 
        AND column_name = 'webhookSecret'
    ) THEN
        -- Create Webhook records for projects that have webhook secrets
        INSERT INTO "Webhook" (id, "gitRepoUrl", secret, "isActive", "createdAt", "updatedAt")
        SELECT 
            gen_random_uuid() as id,
            "gitRepoUrl",
            "webhookSecret" as secret,
            true as "isActive",
            NOW() as "createdAt",
            NOW() as "updatedAt"
        FROM "Project" 
        WHERE "webhookSecret" IS NOT NULL 
            AND "webhookSecret" != ''
        GROUP BY "gitRepoUrl", "webhookSecret"
        ON CONFLICT ("gitRepoUrl") DO NOTHING;

        -- Update projects to reference the new webhook records
        UPDATE "Project" 
        SET "webhookId" = (
            SELECT w.id 
            FROM "Webhook" w 
            WHERE w."gitRepoUrl" = "Project"."gitRepoUrl"
        )
        WHERE "webhookSecret" IS NOT NULL 
            AND "webhookSecret" != '';

        -- Remove the webhookSecret column from Project table
        ALTER TABLE "Project" DROP COLUMN "webhookSecret";
    END IF;
END $$;