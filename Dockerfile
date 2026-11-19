FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY interface ./interface
COPY config ./config
COPY ontology ./ontology
RUN pip install --no-cache-dir .
ENV ONTOLOGY_FILE=/app/ontology/bank.yaml
ENV MCP_HOST=0.0.0.0
RUN mkdir -p reports && chown 1000 reports   # review queue (SQLite) lives here
USER 1000
EXPOSE 8000
CMD ["uvicorn", "secure_sql_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
