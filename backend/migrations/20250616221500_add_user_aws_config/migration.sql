-- CreateTable
CREATE TABLE "UserAWSConfig" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "awsAccessKeyId" TEXT NOT NULL,
    "awsSecretAccessKey" TEXT NOT NULL,
    "awsRegion" TEXT NOT NULL DEFAULT 'us-east-1',
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "UserAWSConfig_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "UserAWSConfig_userId_key" ON "UserAWSConfig"("userId");

-- AddForeignKey
ALTER TABLE "UserAWSConfig" ADD CONSTRAINT "UserAWSConfig_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;