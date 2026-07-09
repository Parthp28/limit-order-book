from collections import deque
from sortedcontainers import SortedDict
from src.order import Order, Side, OrderStatus


class OrderBook:
    """
    Price-time priority limit order book.

    bids: SortedDict with negated key → highest price first (best bid = index 0)
    asks: SortedDict with default key → lowest price first (best ask = index 0)
    order_lookup: dict[order_id → Order] for O(1) cancel via lazy deletion
    """

    def __init__(self):
        # Interview signal: why lambda x: -x?
        # SortedDict sorts ascending by default. Negating the key reverses it.
        # Best bid (highest price) is always at index 0.
        self.bids: SortedDict = SortedDict(lambda x: -x)
        self.asks: SortedDict = SortedDict()
        self.order_lookup: dict[str, Order] = {}

    def add_limit_order(self, order: Order) -> None:
        """
        Add a limit order to the correct side at the correct price level.
        Time complexity: O(log n) where n = number of distinct price levels.
        """
        # Interview signal: what is price-time priority?
        # Same price = time priority. deque maintains FIFO = time priority.
        book = self.bids if order.side == Side.BUY else self.asks
        if order.price not in book:
            book[order.price] = deque()
        book[order.price].append(order)
        self.order_lookup[order.order_id] = order

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order using lazy deletion.
        Sets status = CANCELLED. Does NOT remove from deque.
        Time complexity: O(1).
        """
        # Interview signal: why lazy deletion?
        # deque has no O(1) remove-by-index. Scanning = O(n). Lazy = O(1).
        # Cleanup happens naturally when matching engine sweeps the level.
        if order_id not in self.order_lookup:
            return False
        self.order_lookup[order_id].status = OrderStatus.CANCELLED
        return True

    def modify_order(self, order_id: str,
                     new_quantity: int = None,
                     new_price: float = None) -> bool:
        """
        Modify quantity (in-place, keeps time priority) or price (cancel + reinsert,
        loses time priority — correct behavior per exchange rules).
        Time complexity: O(1) for qty change, O(log n) for price change.
        """
        # Interview signal: why does price change lose time priority?
        # You are effectively cancelling and placing a new order.
        # Keeping priority would be unfair to other participants.
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
        """O(1) — SortedDict with negated key puts highest price at index 0."""
        return self.bids.keys()[0] if self.bids else None

    def get_best_ask(self) -> float | None:
        """O(1) — SortedDict puts lowest price at index 0."""
        return self.asks.keys()[0] if self.asks else None

    def get_mid_price(self) -> float | None:
        """(best_bid + best_ask) / 2. None if either side empty. Time complexity: O(1)."""
        bid = self.get_best_bid()
        ask = self.get_best_ask()
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2

    def get_spread(self) -> float | None:
        """best_ask - best_bid. None if either side empty. Time complexity: O(1)."""
        bid = self.get_best_bid()
        ask = self.get_best_ask()
        if bid is None or ask is None:
            return None
        return ask - bid

    def get_depth(self, side: Side, levels: int = 5) -> list[tuple[float, int]]:
        """
        Top N price levels with total quantity at each level.
        Returns: [(price, total_qty), ...]
        Time complexity: O(levels * avg_orders_per_level)
        """
        # Interview signal: what is order book depth?
        # Depth shows liquidity at each price level.
        # Thin depth = large orders move the price more (market impact).
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
        """Remove price level if deque is empty. Called after matching. Time complexity: O(log n)."""
        if price in book and len(book[price]) == 0:
            del book[price]
