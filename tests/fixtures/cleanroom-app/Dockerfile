# syntax=docker/dockerfile:1
FROM node:24-slim
ENV NODE_ENV=production
WORKDIR /app
COPY server.js ./
USER node
EXPOSE 3000
HEALTHCHECK --interval=3s --timeout=3s --start-period=5s --retries=10 \
  CMD node -e "fetch('http://127.0.0.1:3000/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server.js"]
