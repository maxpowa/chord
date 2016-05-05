import sys

from twisted.internet import reactor

from cord.client import Client
from cord.util import start_logging
start_logging()

cli = Client(reactor=reactor)

@cli.event
def on_ready(data):
    print('dickbutts')


@cli.event
def on_presence_update(data):
    print('p update')


if __name__ == "__main__":
    moot = cli.login_and_connect('maxpowa1@gmail.com', 'notmypass')

    def done(ignored):
        if moot.running:
            moot.stop()

    cli.deferred.addBoth(done)
    moot.run()
