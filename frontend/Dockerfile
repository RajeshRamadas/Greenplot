# Build context is the repository root so the public site (index.html) is included:
#   docker build -f frontend/Dockerfile .
FROM node:22-alpine AS build
# Rewrites are resolved at build time, so the API address is a build argument.
ARG GREENPLOT_API_URL=http://api:8000
ENV GREENPLOT_API_URL=$GREENPLOT_API_URL
# Public address used for canonical links, the sitemap and share tags; also read at build time.
ARG NEXT_PUBLIC_SITE_URL=https://greenplot.in
ENV NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL
WORKDIR /repo/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY index.html /repo/index.html
COPY frontend/ ./
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
# The plant store pages read the catalogue from the API on the server, at request time.
ARG GREENPLOT_API_URL=http://api:8000
ENV GREENPLOT_API_URL=$GREENPLOT_API_URL
COPY --from=build /repo/frontend/.next/standalone ./
COPY --from=build /repo/frontend/.next/static ./.next/static
COPY --from=build /repo/frontend/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
