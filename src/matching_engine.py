from src.order import Order, Fill, Side, OrderType, OrderStatus
from src.order_book import OrderBook


class MatchingEngine:
    """
    Executes orders against the OrderBook. Generates Fill objects.
    Does NOT modify the book directly for data reads —
    modifications happen via order status and deque operations during sweep.
    """

    def __init__(self, order_book: OrderBook):
        self.book = order_book

    def submit_order(self, order: Order) -> list[Fill]:
        """
        Route to correct handler by order type.
        Time complexity: O(handler-specific).
        """
        # Interview signal: why separate handlers?
        # Each order type has different execution semantics.
        # Single function with if-else chains is harder to test and extend.
        dispatch = {
            OrderType.MARKET: self.match_market_order,
            OrderType.LIMIT: self.match_limit_order,
            OrderType.IOC: self.execute_ioc,
            OrderType.FOK: self.execute_fok,
        }
        return dispatch[order.order_type](order)

    def match_market_order(self, order: Order) -> list[Fill]:
        """
        Execute market order at best available prices. Sweep until filled or book empty.
        Time complexity: O(k * m) where k=price levels consumed, m=orders per level.
        """
        # Interview signal: what is "walking the book"?
        # A large market order consuming multiple price levels. Each level = worse price.
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
        """
        Limit order: match immediately if it crosses the spread, then rest in book.
        Time complexity: O(k * m) for aggressive part + O(log n) for resting.
        """
        # Interview signal: when does a limit order match immediately?
        # Limit BUY at 100.60 when best ask is 100.50 → crosses spread → matches now.
        # Fill price = 100.50 (maker's price), NOT 100.60 (your limit).
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
        """
        Immediate-Or-Cancel: fill as much as possible now. Discard remainder.
        Does NOT add remainder to book.
        Time complexity: O(k * m) where k=price levels consumed, m=orders per level.
        """
        # Interview signal: IOC vs FOK?
        # IOC = best effort fill, cancel rest. FOK = all or nothing.
        fills = self.match_market_order(order)
        return fills

    def execute_fok(self, order: Order) -> list[Fill]:
        """
        Fill-Or-Kill: check if full fill is possible BEFORE executing.
        If not possible: return empty list, book is UNCHANGED.
        Time complexity: O(n * m) pre-check + O(k * m) execution.
        """
        # Interview signal: why check first?
        # A partial execution followed by cancel would modify the book.
        # FOK must leave the book unchanged on failure.
        if self._available_quantity(order) < order.quantity:
            return []
        return self.match_market_order(order)

    def _available_quantity(self, order: Order) -> int:
        """
        Count available quantity on opposing side at crossable prices.
        Does NOT execute anything. Used by FOK pre-check.
        Time complexity: O(n * m) where n=levels, m=orders per level.
        """
        opposing = self.book.asks if order.side == Side.BUY else self.book.bids
        available = 0
        for price, level in opposing.items():
            for o in level:
                if o.status == OrderStatus.ACTIVE:
                    available += o.quantity
            if available >= order.quantity:
                return available
        return available
