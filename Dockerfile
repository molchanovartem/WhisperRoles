FROM node:22-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev

COPY server.mjs client.mjs ./

ENV RESULTS_DIR=/data/results

EXPOSE 8000

VOLUME ["/data"]

CMD ["node", "server.mjs"]
