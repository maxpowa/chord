import sys

from twisted.python import log
from twisted.internet import defer, ssl, reactor

log.startLogging(sys.stdout)

from cord.protocol import DiscordClientFactory
from cord import util
from cord.errors import GatewayError, HTTPError, LoginError, WSReconnect, WSError

class Client(object):

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
            raise ValueError('Email and password must be specified to fetch token.')
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

        self.deferred = defer.succeed(email)
        self.deferred.addCallback(self.fetch_token, password)
        self.deferred.addCallback(self.set_token)
        self.deferred.addCallback(self.fetch_gateway)
        self.deferred.addCallback(self.set_gateway)
        self.deferred.addCallback(self.connect)

        def handle_ws_error(failure):
            failure.trap(WSError)
            print(str(failure.value))

        self.deferred.addErrback(handle_ws_error)

        return self.reactor

    def connect(self, gateway=None):
        self.gateway = self.gateway if gateway is None else gateway
        return self._connect()

    def _connect(self):
        if self.token is None or self.token == '':
            raise ValueError('Invalid token, try using fetch_token first.')

        self.factory = DiscordClientFactory(self.gateway, reactor=self.reactor)
        self.factory.token = self.token

        def handle_reconnect(failure):
            failure.trap(WSReconnect)
            return self._connect()
        self.factory.deferred.addErrback(handle_reconnect)

        if self.factory.isSecure:
            self.reactor.connectSSL(self.factory.host,
                                    self.factory.port,
                                    self.factory,
                                    ssl.ClientContextFactory())
        else:
            self.reactor.connectTCP(factory.host,
                                    factory.port,
                                    factory)
        return self.factory.deferred

    def handle_error(self, failure):
        #failure.trap(GatewayError, HTTPError, LoginError)
        print(str(failure.value))
