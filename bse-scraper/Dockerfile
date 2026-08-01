FROM node:18-alpine
WORKDIR /app

# Copy package files
COPY bse-scraper/package*.json ./
RUN npm install

# Copy source code
COPY bse-scraper/ ./

CMD ["node", "server.js"]
