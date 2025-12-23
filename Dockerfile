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
#CMD gunicorn --workers 1 --threads 4 --timeout 120 app:app --bind 0.0.0.0:$PORT
# Timeout বাড়িয়ে 300 সেকেন্ড (৫ মিনিট) করা হলো
CMD gunicorn --workers 1 --threads 4 --timeout 300 --keep-alive 300 app:app --bind 0.0.0.0:$PORT
