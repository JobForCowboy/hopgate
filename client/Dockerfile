FROM python:3.12-slim
WORKDIR /app
COPY core.py adapters.py cli.py ./
ENTRYPOINT ["python", "cli.py"]
CMD ["status"]
