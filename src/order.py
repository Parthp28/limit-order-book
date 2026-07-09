from dataclasses import dataclass, field
from enum import Enum
import time


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    IOC = "IOC"    # Immediate-Or-Cancel: fill what you can, cancel the rest
    FOK = "FOK"    # Fill-Or-Kill: fill everything or fill nothing


class OrderStatus(Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"    # lazy deletion flag — order stays in deque
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"


@dataclass
class Order:
    # Interview signal: why nanoseconds? microsecond-level ordering matters
    # in price-time priority. time.time() returns float seconds — not precise enough.
    order_id: str
    side: Side
    price: float                  # 0.0 for market orders
    quantity: int                 # REMAINING unfilled quantity — decremented on partial fill
    order_type: OrderType
    timestamp: int = field(default_factory=time.time_ns)    # nanosecond precision
    status: OrderStatus = field(default=OrderStatus.ACTIVE)
    filled_quantity: int = field(default=0)                 # total filled so far


@dataclass
class Fill:
    """One execution event. One market order may generate multiple Fills."""
    # Interview signal: maker sets the price. taker is the aggressive order.
    maker_order_id: str     # passive order already in the book
    taker_order_id: str     # aggressive order that just arrived
    price: float            # always the maker's price — maker sets the price
    quantity: int           # shares filled in this single execution
    timestamp: int = field(default_factory=time.time_ns)
