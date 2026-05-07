# ── Stage 1: Build ──────────────────────────────────────────────
FROM node:18-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --frozen-lockfile

COPY . .

# Vite bakes env vars into the bundle at build time
ARG VITE_API_URL=/api
ARG VITE_SIMLI_API_KEY
ARG VITE_SIMLI_FACE_ID
ARG VITE_LIVEKIT_URL

ENV VITE_API_URL=$VITE_API_URL
ENV VITE_SIMLI_API_KEY=$VITE_SIMLI_API_KEY
ENV VITE_SIMLI_FACE_ID=$VITE_SIMLI_FACE_ID
ENV VITE_LIVEKIT_URL=$VITE_LIVEKIT_URL

RUN npm run build

# ── Stage 2: Serve with nginx ────────────────────────────────────
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
