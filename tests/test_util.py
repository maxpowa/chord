import sys

from twisted.python import log
from twisted.internet import defer, ssl, reactor

log.startLogging(sys.stdout)

from cord.protocol import DiscordClientFactory
from cord.util import get_token, get_gateway
from cord.errors import GatewayError, HTTPError, LoginError


if __name__ == "__main__":
    def error(failure):
        #failure.trap(GatewayError, HTTPError, LoginError)
        print(str(failure.value))

    def create_client(gateway, token):
        factory = DiscordClientFactory(gateway, reactor=reactor)
        factory.token = token
        if factory.isSecure:
            reactor.connectSSL(factory.host, factory.port, factory, ssl.ClientContextFactory())
        else:
            reactor.connectTCP(factory.host, factory.port, factory)
        return factory.deferred

    def got_gateway(gateway, token):
        print(repr([gateway, token]))
        return create_client(gateway, token)

    def got_token(token):
        d = get_gateway(reactor, token)
        d.addCallback(got_gateway, token)
        return d

    d = get_token(reactor, 'maxpowa1@gmail.com', 'notpass')
    d.addCallback(got_token)
    d.addErrback(error)

    def all_done(ignored):
        print('Tests did something...')
        reactor.stop()

    d.addCallback(all_done)
    reactor.run()
