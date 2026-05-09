FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml .
COPY README.md .
COPY agent_evolver/ ./agent_evolver/

# Install dependencies
RUN uv pip install --system -e "."

EXPOSE 30000 30001

CMD ["evolver-proxy"]
