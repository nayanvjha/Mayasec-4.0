# Build Stage
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files
COPY package.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY public ./public
COPY src ./src

# Build React app
ARG REACT_APP_API_URL
ARG REACT_APP_ADMIN_TOKEN
ENV REACT_APP_API_URL=$REACT_APP_API_URL
ENV REACT_APP_ADMIN_TOKEN=$REACT_APP_ADMIN_TOKEN
RUN npm run build

# Runtime Stage — Nginx with API reverse proxy
FROM nginx:alpine

# Remove default Nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom Nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built React app from builder
COPY --from=builder /app/build /usr/share/nginx/html

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=10s \
  CMD wget -q --spider http://localhost:3000/health || exit 1

# Run Nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
