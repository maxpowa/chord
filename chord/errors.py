class CordError(Exception):
    pass


class GatewayError(CordError):
    pass


class LoginError(CordError):
    pass


class HTTPError(CordError):
    pass


class RateLimitError(HTTPError):
    pass


class WSError(CordError):
    pass


class WSReconnect(CordError):
    pass
