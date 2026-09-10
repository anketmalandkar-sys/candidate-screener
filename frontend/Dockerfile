# Build the SPA, then serve it (and reverse-proxy /api) with Caddy.
# Base images are multi-arch; Docker selects linux/arm64 automatically on the Pi.

FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
EXPOSE 80
