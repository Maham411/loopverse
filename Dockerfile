# SmogGuard AI - works on Render (uses $PORT) and Hugging Face Spaces (port 7860).
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
EXPOSE 7860
# GROQ_API_KEY is optional and must be set as a secret in the hosting dashboard, never in this file.
CMD ["sh", "-c", "uvicorn app.server:app --host 0.0.0.0 --port ${PORT:-7860}"]
