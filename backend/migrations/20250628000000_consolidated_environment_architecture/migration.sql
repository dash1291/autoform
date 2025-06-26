-- CreateEnum
CREATE TYPE "EnvironmentStatus" AS ENUM ('CREATED', 'PROVISIONING', 'DEPLOYING', 'DEPLOYED', 'FAILED', 'DELETING');

-- AlterTable
ALTER TABLE "Project" ADD COLUMN     "webhookConfigured" BOOLEAN NOT NULL DEFAULT false;

-- AlterTable
ALTER TABLE "Deployment" ADD COLUMN     "environmentId" TEXT;

-- CreateTable
CREATE TABLE "Environment" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "projectId" TEXT NOT NULL,
    "teamAwsConfigId" TEXT NOT NULL,
    "status" "EnvironmentStatus" NOT NULL DEFAULT 'CREATED',
    "branch" TEXT NOT NULL DEFAULT 'main',
    "cpu" INTEGER NOT NULL DEFAULT 256,
    "memory" INTEGER NOT NULL DEFAULT 512,
    "diskSize" INTEGER NOT NULL DEFAULT 21,
    "existingVpcId" TEXT,
    "existingSubnetIds" TEXT,
    "existingClusterArn" TEXT,
    "ecsClusterArn" TEXT,
    "ecsServiceArn" TEXT,
    "albArn" TEXT,
    "albName" TEXT,
    "domain" TEXT,
    "taskDefinitionArn" TEXT,
    "secretsArn" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Environment_pkey" PRIMARY KEY ("id")
);

-- AlterTable
ALTER TABLE "EnvironmentVariable" ADD COLUMN     "environmentId" TEXT NOT NULL;

-- DropIndex
DROP INDEX "TeamAWSConfig_teamId_key";

-- AlterTable
ALTER TABLE "TeamAWSConfig" ADD COLUMN     "name" TEXT NOT NULL DEFAULT 'default';

-- CreateIndex
CREATE UNIQUE INDEX "Environment_projectId_name_key" ON "Environment"("projectId", "name");

-- CreateIndex
CREATE UNIQUE INDEX "TeamAWSConfig_teamId_name_key" ON "TeamAWSConfig"("teamId", "name");

-- AddForeignKey
ALTER TABLE "Deployment" ADD CONSTRAINT "Deployment_environmentId_fkey" FOREIGN KEY ("environmentId") REFERENCES "Environment"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Environment" ADD CONSTRAINT "Environment_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Environment" ADD CONSTRAINT "Environment_teamAwsConfigId_fkey" FOREIGN KEY ("teamAwsConfigId") REFERENCES "TeamAWSConfig"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "EnvironmentVariable" ADD CONSTRAINT "EnvironmentVariable_environmentId_fkey" FOREIGN KEY ("environmentId") REFERENCES "Environment"("id") ON DELETE CASCADE ON UPDATE CASCADE;