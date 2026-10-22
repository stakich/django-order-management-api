class OrderNotFoundError(Exception):
    """Order does not exist or user cannot access it."""
    pass


class OrderCannotBeCancelledError(Exception):
    """Order status does not allow cancellation."""
    pass