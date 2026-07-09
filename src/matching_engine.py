from src.order import Order, Fill, Side, OrderType, OrderStatus
from src.order_book import OrderBook


class MatchingEngine:
    """Runs orders against the book and returns fills."""

    def __init__(self, order_book: OrderBook):
        self.book = order_book

    def submit_order(self, order: Order) -> list[Fill]:
        """Route by order type. O(handler-specific)."""
        # Why: separate handlers? Different semantics per type, easier to test.
        dispatch = {
            OrderType.MARKET: self.match_market_order,
            OrderType.LIMIT: self.match_limit_order,
            OrderType.IOC: self.execute_ioc,
            OrderType.FOK: self.execute_fok,
        }
        return dispatch[order.order_type](order)

    def match_market_order(self, order: Order) -> list[Fill]:
        """Sweep book at best prices until filled or empty. O(k * m)."""
        # Why: walking the book? Large market orders eat multiple price levels.
        opposing = self.book.asks if order.side == Side.BUY else self.book.bids
        fills = []
        remaining = order.quantity

        while remaining > 0 and opposing:
            best_price = opposing.keys()[0]
            level = opposing[best_price]

            while level and remaining > 0:
                maker = level[0]

                if maker.status == OrderStatus.CANCELLED:
                    level.popleft()
                    continue

                fill_qty = min(maker.quantity, remaining)
                fills.append(Fill(
                    maker_order_id=maker.order_id,
                    taker_order_id=order.order_id,
                    price=best_price,
                    quantity=fill_qty,
                ))

                maker.quantity -= fill_qty
                maker.filled_quantity += fill_qty
                remaining -= fill_qty
                order.filled_quantity += fill_qty

                if maker.quantity == 0:
                    maker.status = OrderStatus.FILLED
                    level.popleft()
                    del self.book.order_lookup[maker.order_id]
                else:
                    maker.status = OrderStatus.PARTIALLY_FILLED

            if not level:
                del opposing[best_price]

        order.quantity = remaining
        if remaining == 0:
            order.status = OrderStatus.FILLED
        elif order.filled_quantity > 0:
            order.status = OrderStatus.PARTIALLY_FILLED

        return fills

    def match_limit_order(self, order: Order) -> list[Fill]:
        """Match if crossing spread, rest remainder. O(k * m) + O(log n)."""
        # Why: when does limit match? Buy at 100.60 vs ask 100.50 crosses now.
        # Fill at maker price 100.50, not your limit.
        opposing = self.book.asks if order.side == Side.BUY else self.book.bids
        fills = []
        remaining = order.quantity

        while remaining > 0 and opposing:
            best_price = opposing.keys()[0]

            if order.side == Side.BUY and best_price > order.price:
                break
            if order.side == Side.SELL and best_price < order.price:
                break

            level = opposing[best_price]
            while level and remaining > 0:
                maker = level[0]
                if maker.status == OrderStatus.CANCELLED:
                    level.popleft()
                    continue

                fill_qty = min(maker.quantity, remaining)
                fills.append(Fill(
                    maker_order_id=maker.order_id,
                    taker_order_id=order.order_id,
                    price=best_price,
                    quantity=fill_qty,
                ))

                maker.quantity -= fill_qty
                maker.filled_quantity += fill_qty
                remaining -= fill_qty
                order.filled_quantity += fill_qty

                if maker.quantity == 0:
                    maker.status = OrderStatus.FILLED
                    level.popleft()
                    del self.book.order_lookup[maker.order_id]
                else:
                    maker.status = OrderStatus.PARTIALLY_FILLED

            if not level:
                del opposing[best_price]

        order.quantity = remaining
        if remaining == 0:
            order.status = OrderStatus.FILLED
        elif order.filled_quantity > 0:
            order.status = OrderStatus.PARTIALLY_FILLED
            self.book.add_limit_order(order)
        else:
            self.book.add_limit_order(order)

        return fills

    def execute_ioc(self, order: Order) -> list[Fill]:
        """Fill now, discard remainder. O(k * m)."""
        # Why: IOC vs FOK? IOC fills what it can. FOK is all or nothing.
        fills = self.match_market_order(order)
        return fills

    def execute_fok(self, order: Order) -> list[Fill]:
        """Pre-check full fill, execute or kill. O(n * m) + O(k * m)."""
        # Why: check first? Partial fill would change the book on failure.
        if self._available_quantity(order) < order.quantity:
            return []
        return self.match_market_order(order)

    def _available_quantity(self, order: Order) -> int:
        """Count opposing active qty for FOK pre-check. O(n * m)."""
        opposing = self.book.asks if order.side == Side.BUY else self.book.bids
        available = 0
        for price, level in opposing.items():
            for o in level:
                if o.status == OrderStatus.ACTIVE:
                    available += o.quantity
            if available >= order.quantity:
                return available
        return available
