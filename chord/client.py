from twisted.internet import defer, ssl
from twisted.internet.endpoints import SSL4ClientEndpoint, TCP4ClientEndpoint

from twisted.logger import Logger

from chord.protocol import DiscordClientFactory, EventHandler
from chord.util import get_token, get_gateway
from chord.errors import LoginError, WSReconnect


class BaseClient(EventHandler):
    log = Logger()

    def dispatch(self, event, *args, **kwargs):
        raise NotImplementedError('dispatch not implemented')

    def handle_event(self, event, data):
        self.dispatch(event, data)


class Client(BaseClient):
    def __init__(self, reactor=None, token=None):
        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor
        self.token = token

    def get_reactor(self):
        return self.reactor

    def get_token(self):
        return self.token

    def fetch_token(self, email=None, password=None):
        if email is None or password is None:
            raise LoginError('Email and password must be specified to fetch token.')
        d = get_token(email, password, reactor=self.reactor)
        d.addCallback(self.set_token)
        return d

    def set_token(self, token):
        self.token = token
        return defer.succeed(self.token)

    def fetch_gateway(self, token=None):
        self.token = self.token if token is None else token
        d = get_gateway(self.token, reactor=self.reactor)
        d.addCallback(self.set_gateway)
        return d

    def set_gateway(self, gateway):
        self.gateway = gateway
        return defer.succeed(self.gateway)

    def login(self, email, password, reactor=None):
        self.reactor = self.reactor if reactor is None else reactor

        self.deferred = self.fetch_token(email, password)
        self.deferred.addCallback(self.fetch_gateway)

        self.deferred.addErrback(self.handle_error)

        return self.deferred

    def login_and_connect(self, *args, **kwargs):
        self.deferred = self.login(*args, **kwargs)
        self.deferred.addCallback(self.connect)

        self.deferred.addErrback(self.handle_error)

        return self.reactor

    def connect(self, gateway=None):
        self.gateway = self.gateway if gateway is None else gateway
        return self._connect()

    def _connect(self):
        if self.token is None or self.token == '':
            raise LoginError('Invalid token, try using fetch_token first.')

        self.factory = DiscordClientFactory(self.gateway, reactor=self.reactor)
        self.factory.token = self.token

        def handle_reconnect(failure):
            failure.trap(WSReconnect)
            return self._connect()
        self.factory.deferred.addErrback(handle_reconnect)

        if self.factory.isSecure:
            self.endpoint = SSL4ClientEndpoint(self.reactor,
                                               self.factory.host,
                                               self.factory.port,
                                               ssl.ClientContextFactory())
        else:
            self.endpoint = TCP4ClientEndpoint(self.reactor,
                                               self.factory.host,
                                               self.factory.port)
        d = self.endpoint.connect(self.factory)
        d.addCallback(self.set_protocol)
        return self.factory.deferred

    def set_protocol(self, protocol):
        self._protocol = protocol
        self._protocol.add_event_handler(self)
        return defer.succeed(self._protocol)

    def handle_error(self, failure):
        self.log.error(str(failure.value))
        failure.raiseException()

    def event(self, func):
        setattr(self, func.__name__, func)
        self.log.debug('{func.__name__} has successfully been registered as an event', func=func)
        return func

    def dispatch(self, event, *args, **kwargs):
        self.log.debug('Dispatching event {}'.format(event))
        handler = 'on_' + event.lower()

        if hasattr(self, handler):
            defer.maybeDeferred(getattr(self, handler), *args, **kwargs)
        else:
            self.log.error('Unhandled event {event}', event=event)
