# COPYRIGHT (c) 2016 Max Gurela
#
# MIT License
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from __future__ import unicode_literals

from autobahn.twisted.websocket import WebSocketClientProtocol, \
    WebSocketClientFactory

from twisted.internet import defer, task
from twisted.logger import Logger

import random
import json
import sys
import zlib


from cord import __user_agent__
from cord.errors import WSError, WSReconnect


class EventHandler(object):
    def handle_event(self, event, data):
        raise NotImplementedError('handle_event not implemented in client')


class DiscordClientProtocol(WebSocketClientProtocol):
    _log = Logger()

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

    _event_handlers = []
    _ka_task = None
    sequence = 0
    session_id = None

    def onConnect(self, response):
        self._log.debug("Connecting to Discord server: {0}".format(response.peer))

    def onOpen(self):
        self._log.debug("Discord connection opened")
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

        payload = payload.decode('utf8')

        self._log.debug('RECV: {payload}', payload=payload)

        msg = json.loads(payload)

        op = msg.get('op')
        data = msg.get('d')

        if 's' in msg:
            self.sequence = msg.get('s')

        if op == self.RECONNECT:
            self._log.debug('Got RECONNECT')
            self.dropConnection()
            return self.factory.deferred.errback(WSReconnect('RECONNECT Requested'))

        if op == self.INVALIDATE_SESSION:
            self.sequence = 0
            self.session_id = None
            self.identify()
            self._log.debug('Session invalidated')
            return

        if op != self.DISPATCH:
            self._log.debug('Unknown op {op}', op=op)
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

        for handler in self._event_handlers:
            handler.handle_event(event, msg)

    def keepAlive(self):
        self.sendMessage(json.dumps({
            'op': self.HEARTBEAT,
            'd': self.sequence
        }))

    def sendMessage(self, *args, **kwargs):
        self._log.debug('SEND: {payload}', payload=args[0])
        return WebSocketClientProtocol.sendMessage(self, *args, **kwargs)

    def onClose(self, wasClean, code, reason):
        if self._ka_task is not None and self._ka_task.running:
            self._ka_task.stop()

        if wasClean:
            self.factory.deferred.callback(None)
        else:
            self.factory.deferred.errback(WSError("Discord connection closed: {0} {1}".format(code, reason)))

    def add_event_handler(self, handler):
        if not isinstance(handler, EventHandler):
            raise ValueError('Invalid event handler')
        self._event_handlers.append(handler)


class DiscordClientFactory(WebSocketClientFactory):
    protocol = DiscordClientProtocol
    deferred = defer.Deferred()

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
