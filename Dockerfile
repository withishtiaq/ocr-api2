# Python এর হালকা ভার্সন ব্যবহার করছি
FROM python:3.9-slim

# সিস্টেম প্যাকেজ আপডেট এবং Tesseract (Bangla) + Poppler ইনস্টল
RUN apt-get update && \
    apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-ben \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# ওয়ার্কিং ডিরেক্টরি সেট করা
WORKDIR /app

# ফাইলগুলো কপি করা
COPY . .

# পাইথন লাইব্রেরি ইনস্টল করা
RUN pip install --no-cache-dir -r requirements.txt

# Render এর পোর্টে অ্যাপ রান করা
CMD gunicorn app:app --bind 0.0.0.0:$PORT
