FROM python:3.11.3-slim

WORKDIR /app
EXPOSE 8000

COPY ./requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt --no-cache-dir

COPY ./ /app

CMD ["uvicorn", "--host=0.0.0.0", "--port=8000", "prometheus_docker_discovery:app"]
