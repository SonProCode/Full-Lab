FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY client/load_test.py .
ENTRYPOINT ["python", "load_test.py"]
