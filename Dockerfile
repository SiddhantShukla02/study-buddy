FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Data lives in SQLite. Mount a volume and set STUDYBUDDY_DB to keep it across redeploys.
ENV STUDYBUDDY_DB=/tmp/studybuddy.db
EXPOSE 8000
CMD ["python", "server.py"]
