import time
from src.order import Order, Fill, Side, OrderType, OrderStatus
from src.order_book import OrderBook
from src.matching_engine import MatchingEngine
from src.fix_parser import FIXParser, SOH


def test_order_default_status_is_active():
    order = Order("ORD001", Side.BUY, 100.50, 100, OrderType.LIMIT)
    assert order.status == OrderStatus.ACTIVE


def test_order_timestamp_is_nanoseconds():
    order = Order("ORD001", Side.BUY, 100.50, 100, OrderType.LIMIT)
    assert order.timestamp > 1e18


def test_order_filled_quantity_starts_zero():
    order = Order("ORD001", Side.BUY, 100.50, 100, OrderType.LIMIT)
    assert order.filled_quantity == 0


def test_fill_price_is_makers_price():
    """Fill price is always the maker's price, not the taker's limit."""
    fill = Fill(
        maker_order_id="MAKER001",
        taker_order_id="TAKER001",
        price=100.50,
        quantity=50,
    )
    assert fill.price == 100.50


def test_add_limit_buy_appears_in_bids():
    book = OrderBook()
    order = Order("B1", Side.BUY, 100.00, 50, OrderType.LIMIT)
    book.add_limit_order(order)
    assert 100.00 in book.bids
    assert book.bids[100.00][0] is order


def test_add_limit_sell_appears_in_asks():
    book = OrderBook()
    order = Order("S1", Side.SELL, 101.00, 50, OrderType.LIMIT)
    book.add_limit_order(order)
    assert 101.00 in book.asks
    assert book.asks[101.00][0] is order


def test_best_bid_is_highest_price():
    book = OrderBook()
    book.add_limit_order(Order("B1", Side.BUY, 99.00, 10, OrderType.LIMIT))
    book.add_limit_order(Order("B2", Side.BUY, 100.50, 10, OrderType.LIMIT))
    book.add_limit_order(Order("B3", Side.BUY, 100.00, 10, OrderType.LIMIT))
    assert book.get_best_bid() == 100.50


def test_best_ask_is_lowest_price():
    book = OrderBook()
    book.add_limit_order(Order("S1", Side.SELL, 102.00, 10, OrderType.LIMIT))
    book.add_limit_order(Order("S2", Side.SELL, 100.50, 10, OrderType.LIMIT))
    book.add_limit_order(Order("S3", Side.SELL, 101.00, 10, OrderType.LIMIT))
    assert book.get_best_ask() == 100.50


def test_price_time_priority_within_level():
    book = OrderBook()
    first = Order("B1", Side.BUY, 100.00, 10, OrderType.LIMIT)
    second = Order("B2", Side.BUY, 100.00, 20, OrderType.LIMIT)
    book.add_limit_order(first)
    book.add_limit_order(second)
    level = book.bids[100.00]
    assert level[0] is first
    assert level[1] is second


def test_cancel_sets_status_cancelled():
    book = OrderBook()
    order = Order("B1", Side.BUY, 100.00, 10, OrderType.LIMIT)
    book.add_limit_order(order)
    assert book.cancel_order("B1") is True
    assert order.status == OrderStatus.CANCELLED
    assert order in book.bids[100.00]


def test_cancel_nonexistent_returns_false():
    book = OrderBook()
    assert book.cancel_order("MISSING") is False


def test_modify_quantity_keeps_time_priority():
    book = OrderBook()
    first = Order("B1", Side.BUY, 100.00, 100, OrderType.LIMIT)
    second = Order("B2", Side.BUY, 100.00, 50, OrderType.LIMIT)
    book.add_limit_order(first)
    book.add_limit_order(second)
    old_ts = first.timestamp
    assert book.modify_order("B1", new_quantity=60) is True
    assert first.quantity == 60
    assert first.timestamp == old_ts
    assert book.bids[100.00][0] is first


def test_modify_price_reinserts_with_new_timestamp():
    book = OrderBook()
    order = Order("B1", Side.BUY, 100.00, 100, OrderType.LIMIT)
    book.add_limit_order(order)
    old_ts = order.timestamp
    time.sleep(0.001)
    assert book.modify_order("B1", new_price=101.00) is True
    new_order = book.order_lookup["B1"]
    assert new_order.price == 101.00
    assert new_order.timestamp > old_ts
    assert 101.00 in book.bids


def test_spread_is_ask_minus_bid():
    book = OrderBook()
    book.add_limit_order(Order("B1", Side.BUY, 100.00, 10, OrderType.LIMIT))
    book.add_limit_order(Order("S1", Side.SELL, 100.50, 10, OrderType.LIMIT))
    assert book.get_spread() == 0.50


def test_mid_price_is_average():
    book = OrderBook()
    book.add_limit_order(Order("B1", Side.BUY, 100.00, 10, OrderType.LIMIT))
    book.add_limit_order(Order("S1", Side.SELL, 100.50, 10, OrderType.LIMIT))
    assert book.get_mid_price() == 100.25


def test_depth_excludes_cancelled_orders():
    book = OrderBook()
    active = Order("B1", Side.BUY, 100.00, 100, OrderType.LIMIT)
    cancelled = Order("B2", Side.BUY, 100.00, 50, OrderType.LIMIT)
    book.add_limit_order(active)
    book.add_limit_order(cancelled)
    book.cancel_order("B2")
    depth = book.get_depth(Side.BUY, levels=1)
    assert depth == [(100.00, 100)]


def test_empty_price_level_cleanup():
    book = OrderBook()
    book.bids[100.00] = __import__("collections").deque()
    book._remove_empty_level(book.bids, 100.00)
    assert 100.00 not in book.bids


def _make_book_with_asks():
    book = OrderBook()
    engine = MatchingEngine(book)
    return book, engine


def test_market_buy_full_fill():
    book, engine = _make_book_with_asks()
    book.add_limit_order(Order("S1", Side.SELL, 100.50, 100, OrderType.LIMIT))
    taker = Order("M1", Side.BUY, 0.0, 100, OrderType.MARKET)
    fills = engine.submit_order(taker)
    assert len(fills) == 1
    assert fills[0].quantity == 100
    assert taker.status == OrderStatus.FILLED
    assert taker.quantity == 0


def test_market_buy_partial_fill_reduces_maker_quantity():
    book, engine = _make_book_with_asks()
    maker = Order("S1", Side.SELL, 100.50, 100, OrderType.LIMIT)
    book.add_limit_order(maker)
    taker = Order("M1", Side.BUY, 0.0, 30, OrderType.MARKET)
    fills = engine.submit_order(taker)
    assert fills[0].quantity == 30
    assert maker.quantity == 70
    assert maker.status == OrderStatus.PARTIALLY_FILLED


def test_market_buy_sweeps_two_price_levels():
    book, engine = _make_book_with_asks()
    book.add_limit_order(Order("S1", Side.SELL, 100.50, 50, OrderType.LIMIT))
    book.add_limit_order(Order("S2", Side.SELL, 100.60, 50, OrderType.LIMIT))
    taker = Order("M1", Side.BUY, 0.0, 80, OrderType.MARKET)
    fills = engine.submit_order(taker)
    assert len(fills) == 2
    assert sum(f.quantity for f in fills) == 80


def test_market_buy_sweeps_two_price_levels_correct_fill_prices():
    book, engine = _make_book_with_asks()
    book.add_limit_order(Order("S1", Side.SELL, 100.50, 50, OrderType.LIMIT))
    book.add_limit_order(Order("S2", Side.SELL, 100.60, 50, OrderType.LIMIT))
    taker = Order("M1", Side.BUY, 0.0, 80, OrderType.MARKET)
    fills = engine.submit_order(taker)
    assert fills[0].price == 100.50
    assert fills[1].price == 100.60


def test_market_order_exceeds_book_depth_returns_partial_fills():
    book, engine = _make_book_with_asks()
    book.add_limit_order(Order("S1", Side.SELL, 100.50, 30, OrderType.LIMIT))
    taker = Order("M1", Side.BUY, 0.0, 100, OrderType.MARKET)
    fills = engine.submit_order(taker)
    assert sum(f.quantity for f in fills) == 30
    assert taker.quantity == 70
    assert taker.status == OrderStatus.PARTIALLY_FILLED


def test_market_sell_hits_bids_highest_first():
    book, engine = _make_book_with_asks()
    book.add_limit_order(Order("B1", Side.BUY, 99.00, 50, OrderType.LIMIT))
    book.add_limit_order(Order("B2", Side.BUY, 100.00, 50, OrderType.LIMIT))
    taker = Order("M1", Side.SELL, 0.0, 30, OrderType.MARKET)
    fills = engine.submit_order(taker)
    assert fills[0].price == 100.00


def test_limit_order_crosses_spread_matches_immediately():
    book, engine = _make_book_with_asks()
    book.add_limit_order(Order("S1", Side.SELL, 100.50, 50, OrderType.LIMIT))
    taker = Order("L1", Side.BUY, 100.60, 30, OrderType.LIMIT)
    fills = engine.submit_order(taker)
    assert len(fills) == 1
    assert fills[0].price == 100.50
    assert fills[0].quantity == 30
    assert taker.status == OrderStatus.FILLED


def test_limit_order_no_cross_rests_in_book():
    book, engine = _make_book_with_asks()
    book.add_limit_order(Order("S1", Side.SELL, 101.00, 50, OrderType.LIMIT))
    taker = Order("L1", Side.BUY, 100.50, 30, OrderType.LIMIT)
    fills = engine.submit_order(taker)
    assert len(fills) == 0
    assert taker.order_id in book.order_lookup
    assert book.get_best_bid() == 100.50


def test_ioc_partial_fill_remainder_not_in_book():
    book, engine = _make_book_with_asks()
    book.add_limit_order(Order("S1", Side.SELL, 100.50, 30, OrderType.LIMIT))
    taker = Order("I1", Side.BUY, 0.0, 100, OrderType.IOC)
    fills = engine.submit_order(taker)
    assert sum(f.quantity for f in fills) == 30
    assert taker.order_id not in book.order_lookup


def test_ioc_full_fill():
    book, engine = _make_book_with_asks()
    book.add_limit_order(Order("S1", Side.SELL, 100.50, 100, OrderType.LIMIT))
    taker = Order("I1", Side.BUY, 0.0, 50, OrderType.IOC)
    fills = engine.submit_order(taker)
    assert sum(f.quantity for f in fills) == 50
    assert taker.status == OrderStatus.FILLED


def test_fok_full_fill_possible_executes():
    book, engine = _make_book_with_asks()
    book.add_limit_order(Order("S1", Side.SELL, 100.50, 100, OrderType.LIMIT))
    taker = Order("F1", Side.BUY, 0.0, 50, OrderType.FOK)
    fills = engine.submit_order(taker)
    assert sum(f.quantity for f in fills) == 50


def test_fok_impossible_returns_empty_fills():
    book, engine = _make_book_with_asks()
    book.add_limit_order(Order("S1", Side.SELL, 100.50, 30, OrderType.LIMIT))
    taker = Order("F1", Side.BUY, 0.0, 100, OrderType.FOK)
    fills = engine.submit_order(taker)
    assert fills == []


def test_fok_impossible_book_completely_unchanged():
    book, engine = _make_book_with_asks()
    maker = Order("S1", Side.SELL, 100.50, 30, OrderType.LIMIT)
    book.add_limit_order(maker)
    maker_qty_before = maker.quantity
    maker_status_before = maker.status
    taker = Order("F1", Side.BUY, 0.0, 100, OrderType.FOK)
    engine.submit_order(taker)
    assert maker.quantity == maker_qty_before
    assert maker.status == maker_status_before
    assert book.get_best_ask() == 100.50


def test_lazy_deletion_cancelled_maker_skipped():
    book, engine = _make_book_with_asks()
    cancelled = Order("S1", Side.SELL, 100.50, 50, OrderType.LIMIT)
    active = Order("S2", Side.SELL, 100.50, 50, OrderType.LIMIT)
    book.add_limit_order(cancelled)
    book.add_limit_order(active)
    book.cancel_order("S1")
    taker = Order("M1", Side.BUY, 0.0, 50, OrderType.MARKET)
    fills = engine.submit_order(taker)
    assert len(fills) == 1
    assert fills[0].maker_order_id == "S2"
    assert fills[0].quantity == 50


def test_fill_price_is_always_maker_price():
    book, engine = _make_book_with_asks()
    book.add_limit_order(Order("S1", Side.SELL, 100.50, 50, OrderType.LIMIT))
    taker = Order("L1", Side.BUY, 100.60, 30, OrderType.LIMIT)
    fills = engine.submit_order(taker)
    assert fills[0].price == 100.50
    assert fills[0].maker_order_id == "S1"


def test_fix_new_limit_buy_all_fields_correct():
    parser = FIXParser()
    raw = f"8=FIX.4.2{SOH}9=65{SOH}35=D{SOH}11=ORD001{SOH}54=1{SOH}38=100{SOH}40=2{SOH}44=100.50{SOH}59=0{SOH}"
    order = parser.parse(raw)
    assert isinstance(order, Order)
    assert order.order_id == "ORD001"
    assert order.side == Side.BUY
    assert order.quantity == 100
    assert order.price == 100.50
    assert order.order_type == OrderType.LIMIT


def test_fix_new_market_buy_order_type_market():
    parser = FIXParser()
    raw = f"8=FIX.4.2{SOH}35=D{SOH}11=ORD002{SOH}54=1{SOH}38=50{SOH}40=1{SOH}"
    order = parser.parse(raw)
    assert order.order_type == OrderType.MARKET


def test_fix_ioc_time_in_force_3():
    parser = FIXParser()
    raw = f"8=FIX.4.2{SOH}35=D{SOH}11=ORD003{SOH}54=1{SOH}38=50{SOH}40=2{SOH}44=100.00{SOH}59=3{SOH}"
    order = parser.parse(raw)
    assert order.order_type == OrderType.IOC


def test_fix_fok_time_in_force_4():
    parser = FIXParser()
    raw = f"8=FIX.4.2{SOH}35=D{SOH}11=ORD004{SOH}54=1{SOH}38=50{SOH}40=2{SOH}44=100.00{SOH}59=4{SOH}"
    order = parser.parse(raw)
    assert order.order_type == OrderType.FOK


def test_fix_new_sell_side_correct():
    parser = FIXParser()
    raw = f"8=FIX.4.2{SOH}35=D{SOH}11=ORD005{SOH}54=2{SOH}38=50{SOH}40=2{SOH}44=100.00{SOH}"
    order = parser.parse(raw)
    assert order.side == Side.SELL


def test_fix_cancel_orig_order_id_correct():
    parser = FIXParser()
    raw = f"8=FIX.4.2{SOH}35=F{SOH}11=CXL001{SOH}37=ORD001{SOH}"
    result = parser.parse(raw)
    assert result.orig_order_id == "ORD001"
    assert result.order_id == "CXL001"


def test_fix_modify_new_price_correct():
    parser = FIXParser()
    raw = f"8=FIX.4.2{SOH}35=G{SOH}11=MOD001{SOH}37=ORD001{SOH}38=80{SOH}44=101.00{SOH}"
    result = parser.parse(raw)
    assert result.new_price == 101.00
    assert result.new_quantity == 80


def test_fix_missing_required_tag_returns_none():
    parser = FIXParser()
    raw = f"8=FIX.4.2{SOH}35=D{SOH}11=ORD001{SOH}54=1{SOH}"
    assert parser.parse(raw) is None


def test_fix_unknown_msgtype_returns_none():
    parser = FIXParser()
    raw = f"8=FIX.4.2{SOH}35=X{SOH}11=ORD001{SOH}"
    assert parser.parse(raw) is None


def test_fix_checksum_tag_parses_despite_equals_in_value():
    parser = FIXParser()
    raw = f"8=FIX.4.2{SOH}35=D{SOH}11=ORD001{SOH}54=1{SOH}38=100{SOH}40=2{SOH}44=100.50{SOH}10=123=456{SOH}"
    order = parser.parse(raw)
    assert isinstance(order, Order)
    assert order.order_id == "ORD001"
