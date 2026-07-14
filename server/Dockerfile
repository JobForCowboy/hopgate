FROM python:3.12-slim
WORKDIR /app
COPY proxy.py tokens.py ./
# allowlist.txt and tokens.json are bind-mounted at runtime (see docker-compose.yml)
EXPOSE 8443
CMD ["python", "proxy.py", "--listen", ":8443"]
