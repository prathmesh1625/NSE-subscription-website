# Stage 1: Build the React frontend
FROM node:18-alpine AS frontend-builder
WORKDIR /build

# Copy frontend package files
COPY frontend/package*.json ./
RUN npm install

# Copy frontend source files
COPY frontend/ ./

# Set relative VITE_API_URL so it proxies dynamically
ARG VITE_API_URL=/api
ARG VITE_RAZORPAY_KEY_ID=rzp_test_StTN99cLXMwRFa
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_RAZORPAY_KEY_ID=$VITE_RAZORPAY_KEY_ID

RUN npm run build

# Stage 2: Build the Python Flask bot
FROM python:3.10-slim
WORKDIR /app

# Install system dependencies for psycopg2 and database setups.
#
# tesseract-ocr is the OCR engine output.py falls back to for scanned filings
# and newspaper cuttings (pytesseract is only a wrapper — it needs this binary,
# and without it OCR logs a warning once and stays disabled). The -hin language
# data is here so OCR_LANGS=eng+hin is a config change rather than a rebuild:
# results are published in Hindi papers as well as English ones.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-hin \
    && rm -rf /var/lib/apt/lists/*

# Copy python requirements
COPY bot/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy python source files
COPY bot/*.py ./

# Copy database migrations and seeds
COPY database/ /app/nse-website/subscription-portal/database/

# Copy the built frontend dist to the exact path Flask expects
COPY --from=frontend-builder /build/dist /app/nse-website/subscription-portal/frontend/dist

# Expose port
EXPOSE 5000

# Set environment variable for SQLite persistence
ENV BOT_DB_PATH=/app/bot_sqlite/bot_data.db

# Run database setup first, then start Flask
CMD ["sh", "-c", "python setup_portal_db.py && python Bot.py"]
