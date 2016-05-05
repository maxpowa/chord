
import sys

from twisted.web.client import Agent, readBody, ResponseDone
from twisted.internet import defer, protocol
from twisted.web.http_headers import Headers
from twisted.logger import globalLogBeginner, textFileLogObserver, FilteringLogObserver, LogLevelFilterPredicate, LogLevel

from errors import GatewayError, HTTPError, LoginError

import json

from chord import __user_agent__


class StringProducer(object):
    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return defer.succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass


class SimpleReceiver(protocol.Protocol):
    def __init__(self, d):
        self.buf = ''
        self.d = d
    def dataReceived(self, data):
        self.buf += data
    def connectionLost(self, reason):
        if reason.check(ResponseDone):
            self.d.callback(self.buf)
        else:
            self.d.errback(reason)


def start_logging(level=LogLevel.info):
    observers = []

    predicate = LogLevelFilterPredicate(defaultLogLevel=level)
    observers.append(FilteringLogObserver(observer=textFileLogObserver(sys.stdout), predicates=[predicate]))

    globalLogBeginner.beginLoggingTo(observers)


def get_token(email, password, reactor=None):
    if reactor is None:
        from twisted.internet import reactor
    headers = {
        'content-type': ['application/json'],
        'User-Agent': [__user_agent__]
    }
    payload = {
        'email': email,
        'password': password
    }
    payload = json.dumps(payload)

    d = Agent(reactor).request(
        method='POST',
        uri='https://discordapp.com/api/auth/login',
        headers=Headers(headers),
        bodyProducer=StringProducer(payload))

    def cbResponse(body, response):
        if response.code == 400 or response.code == 401:
            raise LoginError('Unauthorized login, maybe incorrect username/password combination? ({response.code})'.format(response=response))
        elif response.code != 200:
            raise HTTPError('Unexpected response from server ({response.code})'.format(response=response))
        res = json.loads(body)
        if 'token' not in res:
            raise LoginError('Login response did not contain the token, did the API change?')
        return res['token']

    def cbWriteBody(response):
        d = defer.Deferred()
        response.deliverBody(SimpleReceiver(d))
        d.addCallback(cbResponse, response)
        return d

    d.addCallback(cbWriteBody)
    return d


def invalidate_token(token, reactor=None):
    if reactor is None:
        from twisted.internet import reactor
    headers = {
        'authorization': [token],
        'content-type': ['application/json'],
        'User-Agent': [__user_agent__]
    }

    d = Agent(reactor).request(
        method='GET',
        uri='https://discordapp.com/api/auth/logout',
        headers=Headers(headers),
        bodyProducer=None)

    def cbResponse(response):
        if response.code != 200:
            raise HTTPError('Did not receive expected response from logout endpoint. ({response.code})'.format(response=response))
        return readBody(response)

    d.addCallback(cbResponse)
    return d


def get_gateway(token, reactor=None):
    if reactor is None:
        from twisted.internet import reactor
    headers = {
        'authorization': [token],
        'content-type': ['application/json'],
        'User-Agent': [__user_agent__]
    }

    d = Agent(reactor).request(
        method='GET',
        uri='https://discordapp.com/api/gateway?encoding=json&v=4',
        headers=Headers(headers),
        bodyProducer=None)

    def cbResponse(response):
        if response.code != 200:
            raise GatewayError('Did not receive expected response from gateway endpoint. ({response.code})'.format(response=response))
        d = readBody(response)
        d.addCallback(cbExtractUrl)
        return d

    def cbExtractUrl(body):
        return json.loads(body)['url']

    d.addCallback(cbResponse)
    return d


def check_token(token, reactor=None):
    if reactor is None:
        from twisted.internet import reactor
    headers = {
        'authorization': [token],
        'content-type': ['application/json'],
        'User-Agent': [__user_agent__]
    }

    d = Agent(reactor).request(
        method='GET',
        uri='https://discordapp.com/api/@me',
        headers=Headers(headers),
        bodyProducer=None)

    def cbResponse(response):
        if response.code != 200:
            raise LoginError('Did not receive expected response from @me endpoint. ({response.code})'.format(response=response))
        d = readBody(response)
        d.addCallback(cbExtractUrl)
        return d

    def cbExtractUrl(body):
        return json.loads(body)['url']

    d.addCallback(cbResponse)
    return d
