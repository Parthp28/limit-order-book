from dataclasses import dataclass
from src.order import Order, Side, OrderType

SOH = '\x01'


@dataclass
class CancelRequest:
    order_id: str
    orig_order_id: str


@dataclass
class ModifyRequest:
    order_id: str
    orig_order_id: str
    new_quantity: int | None = None
    new_price: float | None = None


class FIXParser:
    """
    Parses FIX 4.2 messages.
    Uses tag lookup dict — O(1) per tag vs O(n) if-elif chain.
    """

    SIDE_MAP = {"1": Side.BUY, "2": Side.SELL}
    REQUIRED_NEW_ORDER = {"11", "54", "38", "40"}

    def parse(self, raw: str) -> Order | CancelRequest | ModifyRequest | None:
        """
        Parse raw FIX string. Return None on missing required tags or unknown MsgType.
        Time complexity: O(n) where n = number of fields in message.
        """
        # Interview signal: what is FIX protocol?
        # The messaging standard used by every exchange, broker, trading firm since 1992.
        # Every order you've ever placed eventually becomes a FIX message.
        tags: dict[str, str] = {}
        for field in raw.split(SOH):
            if not field:
                continue
            try:
                idx = field.index("=")
                tags[field[:idx]] = field[idx + 1:]
            except ValueError:
                continue

        msg_type = tags.get("35")
        if msg_type == "D":
            return self._parse_new_order(tags)
        elif msg_type == "F":
            return self._parse_cancel(tags)
        elif msg_type == "G":
            return self._parse_modify(tags)
        return None

    def _parse_new_order(self, tags: dict) -> Order | None:
        """Parse New Order Single (35=D). Time complexity: O(1)."""
        if not self.REQUIRED_NEW_ORDER.issubset(tags.keys()):
            return None

        side = self.SIDE_MAP.get(tags["54"])
        if side is None:
            return None

        ord_type = tags["40"]
        tif = tags.get("59", "0")
        order_type = self._resolve_order_type(ord_type, tif)

        return Order(
            order_id=tags["11"],
            side=side,
            quantity=int(tags["38"]),
            price=float(tags.get("44", "0.0")),
            order_type=order_type,
        )

    def _parse_cancel(self, tags: dict) -> CancelRequest | None:
        """Parse Order Cancel Request (35=F). Time complexity: O(1)."""
        if "11" not in tags or "37" not in tags:
            return None
        return CancelRequest(order_id=tags["11"], orig_order_id=tags["37"])

    def _parse_modify(self, tags: dict) -> ModifyRequest | None:
        """Parse Order Cancel/Replace Request (35=G). Time complexity: O(1)."""
        if "11" not in tags or "37" not in tags:
            return None
        return ModifyRequest(
            order_id=tags["11"],
            orig_order_id=tags["37"],
            new_quantity=int(tags["38"]) if "38" in tags else None,
            new_price=float(tags["44"]) if "44" in tags else None,
        )

    @staticmethod
    def _resolve_order_type(ord_type: str, tif: str) -> OrderType:
        """Map FIX OrdType + TimeInForce to OrderType. Time complexity: O(1)."""
        if ord_type == "1":
            return OrderType.MARKET
        if tif == "3":
            return OrderType.IOC
        if tif == "4":
            return OrderType.FOK
        return OrderType.LIMIT
