# cython: language_level=3
from libc.stdint cimport int64_t
from src.order import Order, Fill, Side, OrderStatus


cdef class CythonMatchingEngine:
  # Why: Cython only on the inner loop? C types cut Python boxing in the hot path.
  cdef object book

  def __init__(self, book):
    self.book = book

  cpdef list match_market_order_fast(self, str taker_id, str side_str, int quantity):
    """Cython market order inner loop. O(k * m)."""
    cdef int remaining = quantity
    cdef int fill_qty
    cdef double fill_price
    cdef list fills = []
    cdef object opposing
    cdef object level
    cdef object maker
    cdef object fill_obj
    cdef str maker_id

    if side_str == "BUY":
      opposing = self.book.asks
    else:
      opposing = self.book.bids

    while remaining > 0 and opposing:
      fill_price = opposing.keys()[0]
      level = opposing[fill_price]

      while level and remaining > 0:
        maker = level[0]

        if maker.status == OrderStatus.CANCELLED:
          level.popleft()
          continue

        fill_qty = min(maker.quantity, remaining)
        maker_id = maker.order_id
        fill_obj = Fill(
          maker_order_id=maker_id,
          taker_order_id=taker_id,
          price=fill_price,
          quantity=fill_qty,
        )
        fills.append(fill_obj)

        maker.quantity -= fill_qty
        maker.filled_quantity += fill_qty
        remaining -= fill_qty

        if maker.quantity == 0:
          maker.status = OrderStatus.FILLED
          level.popleft()
          del self.book.order_lookup[maker_id]
        else:
          maker.status = OrderStatus.PARTIALLY_FILLED

      if not level:
        del opposing[fill_price]

    return fills
