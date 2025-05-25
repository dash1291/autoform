# Multi-stage build for Next.js application
FROM node:18-slim AS base

# Install OpenSSL and other dependencies needed for Prisma
RUN apt-get update && apt-get install -y \
    openssl \
    ca-certificates \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install git, zip, and AWS CLI
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    gnupg \
    software-properties-common \
    unzip \
    zip \
    && rm -rf /var/lib/apt/lists/*

# Install AWS CLI v2 (detect architecture)
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ]; then \
        curl "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o "awscliv2.zip"; \
    else \
        curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"; \
    fi && \
    unzip awscliv2.zip && \
    ./aws/install && \
    rm -rf awscliv2.zip aws/
# Install dependencies only when needed
FROM base AS deps
WORKDIR /app

# Install dependencies based on the preferred package manager
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# Rebuild the source code only when needed
FROM base AS builder
WORKDIR /app

# Copy package files and install all dependencies (including dev dependencies for build)
COPY package.json package-lock.json ./
RUN npm ci

# Copy source code
COPY . .

# Generate Prisma Client for the correct platform
RUN npx prisma generate

# Build the application
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# Production image, copy all the files and run next
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Copy the public folder

RUN mkdir .next

# Automatically leverage output traces to reduce image size
# https://nextjs.org/docs/advanced-features/output-file-tracing
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# Copy Prisma schema and generated client
COPY --from=builder /app/prisma ./prisma
COPY --from=builder /app/node_modules/.prisma ./node_modules/.prisma
COPY --from=builder /app/node_modules/@prisma ./node_modules/@prisma



EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# server.js is created by next build from the standalone output
# https://nextjs.org/docs/pages/api-reference/next-config-js/output
CMD ["node", "server.js"]