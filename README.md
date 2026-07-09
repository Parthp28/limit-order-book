# Limit Order Book Engine

A production-grade price-time priority limit order book engine in Python that processes **715k orders/sec** with **p99 latency of 5.08µs** on the matching hot path.

## Architecture

```
  FIX 4.2 Wire Message
         │
         ▼
  ┌─────────────┐
  │ FIXParser   │  parse tag=value pairs (SOH-delimited)
  └──────┬──────┘
         │ Order / CancelRequest / ModifyRequest
         ▼
  ┌─────────────┐     ┌──────────────────────┐
  │ OrderBook   │◄────│ MatchingEngine       │
  │             │     │  - market orders     │
  │ bids:       │     │  - limit orders      │
  │  SortedDict │     │  - IOC / FOK         │
  │ asks:       │     │  - partial fills     │
  │  SortedDict │     └──────────┬───────────┘
  │ order_lookup│                │
  └─────────────┘                ▼
                          list[Fill]
                    (maker price, qty, ids)
```

## Key design decisions

### SortedDict over heap

| Operation | Heap | SortedDict |
|-----------|------|------------|
| Insert | O(log n) | O(log n) |
| Best price | O(log n) | **O(1)** |
| Cancel | **O(n)** | O(log n) |

Real markets have a cancel:new ratio of roughly 10:1. Cancel performance dominates, so SortedDict wins. Bids use a negated key (`lambda x: -x`) so the highest bid sits at index 0.

### Lazy deletion

`deque` has no O(1) remove-by-value. Scanning to find and remove an order is O(n) per cancel — catastrophic at 500k orders/sec. Instead, cancel sets `status = CANCELLED` on the `Order` object in `order_lookup` (O(1)). The matching engine skips cancelled orders during iteration and `popleft()` cleans them up.

### Cython hot path

Cython compiles only the market-order inner loop (`CythonMatchingEngine.match_market_order_fast`). `cdef int` and `cdef double` eliminate Python boxing in arithmetic-heavy code. SortedDict and deque remain Python objects — realistic speedup is 2–5x on the inner loop only, not the whole engine.

## Benchmark results

Measured on Apple Silicon (Python 3.10, 1M mixed orders, book pre-seeded with 100k orders):

| Stage | Orders/sec | p50 | p95 | p99 |
|-------|-----------|-----|-----|-----|
| Baseline (Python) | 715,545 | 0.62µs | 2.62µs | 5.08µs |
| Cython market-order latency (mean) | — | 3.46µs | — | — |
| Python market-order latency (mean) | — | 5.13µs | — | — |
| Target | 500k+ | — | — | < 5µs |

Cython market-order path: **~28% faster** (4.40µs vs 6.07µs mean per match against a 10k-order book).

## How to run

```bash
pip install -r requirements.txt
python setup.py build_ext --inplace   # optional: Cython hot path
docker compose up                     # runs benchmarks in container
```

## Run tests

```bash
pytest tests/ -v --cov=src
coverage report --fail-under=80
```

## Run benchmarks

```bash
pytest benchmarks/bench_matching.py::test_one_million_orders_throughput -s -v
pytest benchmarks/bench_matching.py --benchmark-only -v
```

## What this demonstrates

This project implements the core matching engine that powers every electronic exchange — price-time priority, partial fills, IOC/FOK semantics, and FIX 4.2 wire protocol parsing. The data structure choices (SortedDict, lazy deletion, deque FIFO) are driven by real market microstructure: cancel-heavy workloads, nanosecond time priority, and maker-price execution rules. Benchmarked at 715k orders/sec with sub-6µs p99 latency in pure Python, with a Cython-optimized hot path for the tightest matching loop. Built to be explained line-by-line in a quant SWE interview at Akuna, IMC, or Chicago Trading Company.
