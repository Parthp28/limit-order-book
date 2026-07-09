import pytest
import random
import time
from src.order import Order, Side, OrderType
from src.order_book import OrderBook
from src.matching_engine import MatchingEngine


def _make_book_with_orders(n: int) -> tuple[OrderBook, MatchingEngine]:
    book = OrderBook()
    engine = MatchingEngine(book)
    for i in range(n):
        side = Side.BUY if random.random() < 0.5 else Side.SELL
        price = round(random.gauss(99.80 if side == Side.BUY else 100.20, 0.20), 2)
        book.add_limit_order(Order(
            order_id=f"SETUP{i:08d}",
            side=side,
            price=max(0.01, price),
            quantity=random.randint(1, 100),
            order_type=OrderType.LIMIT,
        ))
    return book, engine


@pytest.fixture
def populated_book():
    return _make_book_with_orders(10_000)


def test_add_limit_order_latency(benchmark):
    """Latency of a single add_limit_order call."""
    book = OrderBook()
    orders = [
        Order(f"O{i}", Side.BUY, round(100 - random.random(), 2),
              random.randint(1, 100), OrderType.LIMIT)
        for i in range(10_000)
    ]
    idx = {"i": 0}

    def add_one():
        book.add_limit_order(orders[idx["i"] % len(orders)])
        idx["i"] += 1

    benchmark(add_one)


def test_market_order_latency(benchmark, populated_book):
    """Latency of a single market order match against a populated book."""
    book, engine = populated_book
    counter = {"i": 0}

    def match_one():
        counter["i"] += 1
        o = Order(f"MKT{counter['i']}", Side.BUY, 0.0, random.randint(1, 20), OrderType.MARKET)
        engine.submit_order(o)
        book.add_limit_order(Order(
            f"R{counter['i']:010d}", Side.SELL,
            round(100.20 + random.random() * 0.10, 2),
            random.randint(1, 50), OrderType.LIMIT
        ))

    benchmark(match_one)


def test_one_million_orders_throughput():
    """1M mixed orders. Asserts >= 500k orders/sec, prints p50/p95/p99."""
    import statistics

    book, engine = _make_book_with_orders(100_000)
    latencies = []

    for i in range(1_000_000):
        if random.random() < 0.1:
            o = Order(f"M{i}", Side.BUY, 0.0, random.randint(1, 30), OrderType.MARKET)
        else:
            side = Side.BUY if random.random() < 0.5 else Side.SELL
            price = round(random.gauss(99.80 if side == Side.BUY else 100.20, 0.30), 2)
            o = Order(f"L{i}", side, max(0.01, price),
                      random.randint(1, 100), OrderType.LIMIT)

        t0 = time.perf_counter_ns()
        if o.order_type == OrderType.MARKET:
            engine.submit_order(o)
        else:
            book.add_limit_order(o)
        latencies.append(time.perf_counter_ns() - t0)

    latencies.sort()
    n = len(latencies)
    total_sec = sum(latencies) / 1e9

    print(f"\n=== BENCHMARK RESULTS ===")
    print(f"Total orders: {n:,}")
    print(f"Total time:   {total_sec:.2f}s")
    print(f"Throughput:   {n / total_sec:,.0f} orders/sec")
    print(f"p50 latency:  {latencies[int(n * 0.50)] / 1000:.2f}µs")
    print(f"p95 latency:  {latencies[int(n * 0.95)] / 1000:.2f}µs")
    print(f"p99 latency:  {latencies[int(n * 0.99)] / 1000:.2f}µs")

    assert (n / total_sec) >= 500_000, \
        f"Throughput {n/total_sec:,.0f} orders/sec below 500k target"


def test_cython_market_order_latency(benchmark, populated_book):
    """Cython vs Python market order match latency."""
    pytest.importorskip("src.cython_matching_engine")
    from src.cython_matching_engine import CythonMatchingEngine
    book, _ = populated_book
    cython_engine = CythonMatchingEngine(book)
    counter = {"i": 0}

    def match_one():
        counter["i"] += 1
        cython_engine.match_market_order_fast(
            f"MKT{counter['i']}", "BUY", random.randint(1, 20)
        )
        book.add_limit_order(Order(
            f"CR{counter['i']:010d}", Side.SELL,
            round(100.20 + random.random() * 0.10, 2),
            random.randint(1, 50), OrderType.LIMIT
        ))

    benchmark(match_one)
