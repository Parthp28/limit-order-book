from collections import deque
from sortedcontainers import SortedDict
from src.order import Order, Side, OrderStatus


class OrderBook:
    """Price-time priority limit order book."""

    def __init__(self):
        # Why: lambda x: -x? SortedDict sorts ascending. Negate to reverse.
        # Best bid ends up at index 0.
        self.bids: SortedDict = SortedDict(lambda x: -x)
        self.asks: SortedDict = SortedDict()
        self.order_lookup: dict[str, Order] = {}

    def add_limit_order(self, order: Order) -> None:
        """Add limit order to correct side and price. O(log n), n = price levels."""
        # Why: price-time priority? Same price means FIFO via deque.
        book = self.bids if order.side == Side.BUY else self.asks
        if order.price not in book:
            book[order.price] = deque()
        book[order.price].append(order)
        self.order_lookup[order.order_id] = order

    def cancel_order(self, order_id: str) -> bool:
        """Lazy cancel: set CANCELLED, leave in deque. O(1)."""
        # Why: lazy deletion? deque has no O(1) remove. Scanning is O(n).
        # Matching sweeps clean up cancelled orders.
        if order_id not in self.order_lookup:
            return False
        self.order_lookup[order_id].status = OrderStatus.CANCELLED
        return True

    def modify_order(self, order_id: str,
                     new_quantity: int = None,
                     new_price: float = None) -> bool:
        """Qty change in place keeps priority. Price change cancel+reinsert. O(1) or O(log n)."""
        # Why: price change loses time priority? It is effectively a new order.
        if order_id not in self.order_lookup:
            return False
        order = self.order_lookup[order_id]
        if order.status == OrderStatus.CANCELLED:
            return False

        if new_quantity and not new_price:
            if new_quantity >= order.quantity:
                return False
            order.quantity = new_quantity
            return True

        if new_price:
            self.cancel_order(order_id)
            import time as t
            new_order = Order(
                order_id=order_id,
                side=order.side,
                price=new_price,
                quantity=new_quantity or order.quantity,
                order_type=order.order_type,
                timestamp=t.time_ns(),
            )
            self.add_limit_order(new_order)
            return True
        return False

    def get_best_bid(self) -> float | None:
        """Best bid price. O(1)."""
        return self.bids.keys()[0] if self.bids else None

    def get_best_ask(self) -> float | None:
        """Best ask price. O(1)."""
        return self.asks.keys()[0] if self.asks else None

    def get_mid_price(self) -> float | None:
        """Mid price. O(1). None if either side is empty."""
        bid = self.get_best_bid()
        ask = self.get_best_ask()
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2

    def get_spread(self) -> float | None:
        """Spread (ask minus bid). O(1). None if either side is empty."""
        bid = self.get_best_bid()
        ask = self.get_best_ask()
        if bid is None or ask is None:
            return None
        return ask - bid

    def get_depth(self, side: Side, levels: int = 5) -> list[tuple[float, int]]:
        """Top N levels as (price, active qty). O(levels * orders_per_level)."""
        # Why: order book depth? Liquidity per level. Thin depth means more impact.
        book = self.bids if side == Side.BUY else self.asks
        result = []
        for price in list(book.keys())[:levels]:
            active_qty = sum(
                o.quantity for o in book[price]
                if o.status == OrderStatus.ACTIVE
            )
            if active_qty > 0:
                result.append((price, active_qty))
        return result

    def _remove_empty_level(self, book: SortedDict, price: float) -> None:
        """Drop empty price level after matching. O(log n)."""
        if price in book and len(book[price]) == 0:
            del book[price]
