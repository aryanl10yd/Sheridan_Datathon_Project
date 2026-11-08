FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package*.json ./
RUN npm ci
COPY index.html vite.config.ts tsconfig.json ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=3000 HOST=0.0.0.0 PYTHON=python
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY device ./device
COPY run.sh ./run.sh
RUN chmod +x run.sh
COPY --from=frontend /build/dist ./dist
EXPOSE 3000
CMD ["./run.sh"]
