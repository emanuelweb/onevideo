# Etapa 1: build de la SPA con Vite
FROM node:22-alpine AS build
WORKDIR /app

# URLs públicas inyectadas en tiempo de build (ver .env.example en la raíz)
ARG VITE_API_URL
ARG VITE_STREAM_URL
ENV VITE_API_URL=${VITE_API_URL} \
    VITE_STREAM_URL=${VITE_STREAM_URL}

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

# Etapa 2: servidor estático nginx con fallback SPA
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
