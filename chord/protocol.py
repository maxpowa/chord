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

from twisted.internet import defer, task, error
from twisted.logger import Logger

import random
import json
import sys
import zlib


from chord import __user_agent__
from chord.errors import WSError, WSReconnect


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

    def __init__(self, *args, **kwargs):
        WebSocketClientProtocol.__init__(self, *args, **kwargs)
        self._event_handlers = []

    def onConnect(self, response):
        self._log.debug("Connecting to Discord server: {0}".format(response.peer))

    def onOpen(self):
        self._log.debug("Discord connection opened")
        # Reset factory reconnect delay
        self.factory.resetDelay()
        self.identify()

    def identify(self):
        payload = {
            'op': self.IDENTIFY,
            'd': {
                'token': self.factory.token,
                'properties': {
                    '$os': sys.platform,
                    '$browser': 'chordlib',
                    '$device': 'chordlib',
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

        #self._log.debug('RECV: {payload}', payload=payload)

        msg = json.loads(payload)

        op = msg.get('op')
        data = msg.get('d')

        if 's' in msg:
            self.sequence = msg.get('s')

        if op == self.RECONNECT:
            self._log.debug('Got RECONNECT')
            self.sendClose(code=1000, reason='RECONNECT requested')
            return

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

        # if code == 1000 and reason == 'RECONNECT requested':
        #     return self.factory.clientConnectionLost(self.factory.connector, 'Reconnecting to Discord')
        #
        # if wasClean:
        #     # Intentional disconnect.
        #     self.factory.stopTrying()
        #     self.factory.stopFactory()
        # else:
        #     self.factory.clientConnectionFailed(self.factory.connector, "Discord connection closed: {0} {1}".format(code, reason))

    def add_event_handler(self, handler):
        if not isinstance(handler, EventHandler):
            raise ValueError('Invalid event handler')
        if handler not in self._event_handlers:
            self._event_handlers.append(handler)


class DiscordClientFactory(WebSocketClientFactory):
    _log = Logger()

    protocol = DiscordClientProtocol

    pending = None

    def __init__(self,
                 url=None,
                 token=None,
                 deferred=None,
                 useragent=__user_agent__,
                 headers=None,
                 proxy=None,
                 reactor=None):
        if reactor is None:
            from twisted.internet import reactor
        self.reactor = reactor
        self.token = token

        if not deferred:
            deferred = defer.Deferred()
        self.deferred = deferred

        self.logOctets = False
        self.logFrames = False
        self.trackTimings = False

        random.seed()
        self.setSessionParameters(url, None, None, useragent, headers, proxy)
        self.resetProtocolOptions()

    def buildProtocol(self, addr):
        p = self.protocol()
        p.factory = self
        self.pending = self.reactor.callLater(
            0, self.fire, self.deferred.callback, p)
        self.deferred = None
        return p

    def __repr__(self):
        clz = self.__class__.__name__
        mem = '0x' + hex(id(self))[2:].zfill(8)
        return '<{0} at {1}: {2}>'.format(clz, mem, self.token)

    def fire(self, func, value):
        """
        Clear C{self.pending} to avoid a reference cycle and then invoke func
        with the value.
        """
        self.pending = None
        func(value)

    # Reconnect

    maxDelay = 3600
    initialDelay = 1.0
    # Note: These highly sensitive factors have been precisely measured by
    # the National Institute of Science and Technology.  Take extreme care
    # in altering them, or you may damage your Internet!
    # (Seriously: <http://physics.nist.gov/cuu/Constants/index.html>)
    factor = 2.7182818284590451 # (math.e)
    # Phi = 1.6180339887498948 # (Phi is acceptable for use as a
    # factor if e is too large for your application.)
    jitter = 0.11962656472 # molar Planck constant times c, joule meter/mole

    delay = initialDelay
    retries = 0
    maxRetries = None
    _callID = None
    connector = None
    clock = None

    continueTrying = True


    def clientConnectionFailed(self, connector, reason):
        self._log.debug('Connection failed, reconnecting... ({})'.format(reason))
        if self.continueTrying:
            self.connector = connector
            self.retry()


    def clientConnectionLost(self, connector, reason):
        self._log.debug('Connection lost, reconnecting... ({})'.format(reason))
        if self.continueTrying:
            self.connector = connector
            self.retry()


    def retry(self, connector=None):
        """
        Have this connector connect again, after a suitable delay.
        """
        if not self.continueTrying:
            if self.noisy:
                self._log.debug("Abandoning %s on explicit request" % (connector,))
            return

        if connector is None:
            if self.connector is None:
                raise ValueError("no connector to retry")
            else:
                connector = self.connector

        self.retries += 1
        if self.maxRetries is not None and (self.retries > self.maxRetries):
            if self.noisy:
                self._log.debug("Abandoning %s after %d retries." %
                        (connector, self.retries))
            return

        self.delay = min(self.delay * self.factor, self.maxDelay)
        if self.jitter:
            self.delay = random.normalvariate(self.delay,
                                              self.delay * self.jitter)

        if self.noisy:
            self._log.debug("%s will retry in %d seconds" % (connector, self.delay,))

        def reconnector():
            self._callID = None
            connector.connect()
        if self.clock is None:
            from twisted.internet import reactor
            self.clock = reactor
        self._callID = self.clock.callLater(self.delay, reconnector)


    def stopTrying(self):
        """
        Put a stop to any attempt to reconnect in progress.
        """
        # ??? Is this function really stopFactory?
        if self._callID:
            self._callID.cancel()
            self._callID = None
        self.continueTrying = 0
        if self.connector:
            try:
                self.connector.stopConnecting()
            except error.NotConnectingError:
                pass


    def resetDelay(self):
        """
        Call this method after a successful connection: it resets the delay and
        the retry counter.
        """
        self.delay = self.initialDelay
        self.retries = 0
        self._callID = None
        self.continueTrying = 1


    def __getstate__(self):
        """
        Remove all of the state which is mutated by connection attempts and
        failures, returning just the state which describes how reconnections
        should be attempted.  This will make the unserialized instance
        behave just as this one did when it was first instantiated.
        """
        state = self.__dict__.copy()
        for key in ['connector', 'retries', 'delay',
                    'continueTrying', '_callID', 'clock']:
            if key in state:
                del state[key]
        return state
