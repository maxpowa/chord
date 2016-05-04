
from twisted.internet import reactor
from cord.client import Client

if __name__ == "__main__":
    cli = Client()
    moot = cli.create('maxpowa1@gmail.com', 'notpass')

    def done(ignored):
        print('closing client')
        if moot.running:
            moot.stop()

    cli.deferred.addCallback(done)
    moot.run()
