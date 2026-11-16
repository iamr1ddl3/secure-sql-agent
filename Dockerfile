FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY interface ./interface
COPY config ./config
RUN pip install --no-cache-dir .
USER 1000
EXPOSE 8000
CMD ["uvicorn", "secure_sql_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
