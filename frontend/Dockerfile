# Build the SPA, then serve the static output from nginx.
#
# VITE_* values are compiled into the bundle, so they're build args rather
# than runtime env: rebuild the image to point it at a different API.
FROM node:22-alpine AS build

WORKDIR /app
COPY package*.json ./
RUN npm ci

ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_GOOGLE_CLIENT_ID=
ARG VITE_MICROSOFT_CLIENT_ID=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID \
    VITE_MICROSOFT_CLIENT_ID=$VITE_MICROSOFT_CLIENT_ID

COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
