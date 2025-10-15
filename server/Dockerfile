
FROM python:3.11-slim
WORKDIR /app
COPY server/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY server /app/server
COPY web /app/web
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
