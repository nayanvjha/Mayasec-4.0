FROM python:3.11-slim

WORKDIR /app

COPY victim-web/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY victim-web/ ./
COPY behavior_analyzer.py ./behavior_analyzer.py

EXPOSE 8080

CMD ["python", "app.py"]
