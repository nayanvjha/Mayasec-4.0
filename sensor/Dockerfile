FROM python:3.11-alpine

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn httpx

COPY mayasec-sensor.py /app/mayasec-sensor.py

EXPOSE 8080

CMD ["python", "mayasec-sensor.py"]
