FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["python", "-m", "pytest", "benchmarks/bench_matching.py::test_one_million_orders_throughput", "-s", "-v"]
