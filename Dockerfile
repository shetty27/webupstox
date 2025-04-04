FROM python:3.9
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install websocket-client
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
