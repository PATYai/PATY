# syntax=docker/dockerfile:1
# Multi-stage Next.js build using standalone output mode

FROM node:22-alpine AS base

# Install dependencies only when needed
FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

# Rebuild the source code only when needed
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build the app (standalone output)
RUN npm run build

# Production image — copy only the standalone output
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=8080

# Create a non-privileged user
ARG UID=10001
RUN addgroup --system --gid ${UID} appgroup && \
    adduser --system --uid ${UID} --ingroup appgroup appuser

# Copy standalone output and static assets
COPY --from=builder --chown=appuser:appgroup /app/.next/standalone ./
COPY --from=builder --chown=appuser:appgroup /app/.next/static ./.next/static
COPY --from=builder --chown=appuser:appgroup /app/public ./public

USER appuser

EXPOSE 8080

CMD ["node", "server.js"]
