# syntax=docker/dockerfile:1
FROM node:26-alpine@sha256:8996bb5821d62a8fd9bb27c1cb07462f3fdce6e47d640c6a881ead0b064ce216 AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# The slim variant: core nginx only, without the curl, brotli and expat the full image carries.
FROM nginxinc/nginx-unprivileged:1.31-alpine-slim@sha256:a8cb0f33d51fa107c96fd2bd3a71aaf564ec131e9d2bdf8700944f0ed8b170d7
# Alpine's fixes (musl, zlib) land before a new nginx image does: upgraded, as the api image is.
USER root
RUN apk upgrade --no-cache
USER 101
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --retries=5 CMD ["wget", "-qO-", "http://127.0.0.1:8080/healthz"]
