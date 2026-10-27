from rest_framework.exceptions import APIException

class PaymentOrderNotFoundError(Exception):
    pass


class PaymentNotAllowedError(Exception):
    pass

class PaymentProviderError(Exception):
    pass


class PaymentServiceUnavailable(APIException):
    status_code = 503
    default_detail = "Payment provider temporarily unavailable"
    default_code = "payment_provider_unavailable"