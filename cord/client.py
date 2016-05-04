import sys

from twisted.python import log
from twisted.internet import defer, ssl, reactor
from twisted.internet.endpoints import SSL4ClientEndpoint, TCP4ClientEndpoint

log.startLogging(sys.stdout)

from cord.protocol import DiscordClientFactory, EventHandler
from cord import util
from cord.errors import GatewayError, HTTPError, LoginError, WSReconnect, WSError

class Client(EventHandler):

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
        return util.get_token(self.reactor, email, password)

    def set_token(self, token):
        self.token = token
        return defer.succeed(self.token)

    def fetch_gateway(self, token=None):
        self.token = self.token if token is None else token
        return util.get_gateway(self.reactor, self.token)

    def set_gateway(self, gateway):
        self.gateway = gateway
        return defer.succeed(self.gateway)

    def create(self, email, password, reactor=None):
        self.reactor = self.reactor if reactor is None else reactor

        self.deferred = self.fetch_token(email, password)
        self.deferred.addCallback(self.set_token)
        self.deferred.addCallback(self.fetch_gateway)
        self.deferred.addCallback(self.set_gateway)
        self.deferred.addCallback(self.connect)

        def handle_ws_error(failure):
            failure.trap(WSError)
            print(str(failure.value))

        self.deferred.addErrback(handle_ws_error)
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

    def handle_event(self, protocol, event, data=None):
        parser = 'parse_' + event.lower()

        try:
            func = getattr(self, parser)
        except AttributeError:
            print('Unhandled event {}'.format(event))
        else:
            func(data)

    def handle_error(self, failure):
        print(str(failure.value))
