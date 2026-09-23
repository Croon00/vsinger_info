"""Only confirmed non-delivery is eligible for automatic retry."""


class DeliveryRetryableError(Exception):
    def __init__(self, message: str, *, retry_after: float = 0):
        super().__init__(message)
        self.retry_after = max(0, retry_after)


class DeliveryPermanentError(Exception):
    pass


class DeliverySkippedError(Exception):
    pass


class DeliveryUncertainError(Exception):
    pass
