from dataclasses import dataclass, field
from enum import Enum
import time


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    IOC = "IOC"    # fill what you can, cancel the rest
    FOK = "FOK"    # fill everything or nothing


class OrderStatus(Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"    # lazy deletion flag, order stays in deque
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"


@dataclass
class Order:
    # Why: nanoseconds? microsecond ordering matters for price-time priority.
    # time.time() returns float seconds, not precise enough.
    order_id: str
    side: Side
    price: float                  # 0.0 for market orders
    quantity: int                 # remaining unfilled qty, decremented on partial fill
    order_type: OrderType
    timestamp: int = field(default_factory=time.time_ns)
    status: OrderStatus = field(default=OrderStatus.ACTIVE)
    filled_quantity: int = field(default=0)


@dataclass
class Fill:
    """One fill event. A market order can produce several."""
    # Why: maker sets the price. taker is the aggressive order.
    maker_order_id: str
    taker_order_id: str
    price: float            # always the maker's price
    quantity: int
    timestamp: int = field(default_factory=time.time_ns)
