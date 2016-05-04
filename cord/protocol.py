from __future__ import unicode_literals

from autobahn.twisted.websocket import WebSocketClientProtocol, \
    WebSocketClientFactory

from twisted.internet import task

import random
import json
import sys
import zlib

from errors import WSError

from util import get_gateway, get_token, __user_agent__


class DiscordClientProtocol(WebSocketClientProtocol):
    DISPATCH           = 0
    HEARTBEAT          = 1
    IDENTIFY           = 2
    PRESENCE           = 3
    VOICE_STATE        = 4
    VOICE_PING         = 5
    RESUME             = 6
    RECONNECT          = 7
    REQUEST_MEMBERS    = 8
    INVALIDATE_SESSION = 9

    _ka_task = None
    sequence = 0
    session_id = None

    def onConnect(self, response):
        print("Server connected: {0}".format(response.peer))

    def onOpen(self):
        print("WebSocket connection open.")
        self.identify()

    def identify(self):
        payload = {
            'op': self.IDENTIFY,
            'd': {
                'token': self.factory.token,
                'properties': {
                    '$os': sys.platform,
                    '$browser': 'cordlib',
                    '$device': 'cordlib',
                    '$referrer': '',
                    '$referring_domain': ''
                },
                'compress': True,
                'large_threshold': 250,
                'v': 3
            }
        }
        self.sendMessage(json.dumps(payload))

    def onMessage(self, payload, isBinary):
        if isBinary:
            payload = zlib.decompress(payload, 15, 10490000) # This is 10 MiB

        print('RECV: {}'.format(payload.decode('utf8')))

        payload = payload.decode('utf8')

        msg = json.loads(payload)

        op = msg.get('op')
        data = msg.get('d')

        if 's' in msg:
            self.sequence = msg.get('s')

        if op == self.RECONNECT:
            print('Got RECONNECT')
            self.dropConnection()
            return self.factory.d.errback(WSReconnect('RECONNECT Requested'))

        if op == self.INVALIDATE_SESSION:
            print('Session invalidated')
            return

        if op != self.DISPATCH:
            print('Unknown op {}'.format(op))
            return

        event = msg.get('t')
        if event == 'READY':
            self.sequence = msg.get('s')
            self.session_id = data.get('session_id')

        if event == 'READY' or event == 'RESUMED':
            interval = data.get('heartbeat_interval') / 1000.0
            if self._ka_task is not None and self._ka_task.running:
                self._ka_task.stop()
            self._ka_task = task.LoopingCall(self.keepAlive)
            self._ka_task.start(interval)

    def keepAlive(self):
        self.sendMessage(json.dumps({
            'op': self.HEARTBEAT,
            'd': self.sequence
        }))

    def sendMessage(self, *args, **kwargs):
        print('SEND: {}'.format(args[0]))
        return WebSocketClientProtocol.sendMessage(self, *args, **kwargs)

    def onClose(self, wasClean, code, reason):
        if self._ka_task is not None and self._ka_task.running:
            self._ka_task.stop()
        print("WebSocket connection closed: {0} {1}".format(code, reason))
        self.factory.d.errback(WSError("WebSocket connection closed: {0} {1}".format(code, reason)))


class DiscordClientFactory(WebSocketClientFactory):
    protocol = DiscordClientProtocol

    def __init__(self,
                 url=None,
                 useragent=__user_agent__,
                 headers=None,
                 proxy=None,
                 reactor=None):
        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor
        self.logOctets = False
        self.logFrames = False
        self.trackTimings = False

        random.seed()
        self.setSessionParameters(url, None, None, useragent, headers, proxy)
        self.resetProtocolOptions()


    def setGatewayUrl(self, url):
        (isSecure, host, port, resource, path, params) = parseWsUrl(url or "ws://localhost")
        self.url = url
        self.isSecure = isSecure
        self.host = host
        self.port = port
        self.resource = resource
        self.path = path
        self.params = params


    def setAuthParameters(self, email=None, password=None, token=None):
        if token is not None:
            self.token = token
        elif email is not None and password is not None:
            self.email = email
            self.password = password
        else:
            raise ValueError('You must specify at least token or an email and password combination.')