#!/usr/bin/python
import os
import ch
import ch.mixin


class Bot(ch.mixin.WindowsMainLoopFix, ch.RoomManager):
    # Set backward compatibility behavior flag for older bots
    # using threading for non deterministic modification of tasks or conns (rooms)
    disconnectOnEmptyConnAndTask = False

    def onConnect(self, room):
        print("Connected to "+room.name)
        room.message('successful connection')
        self.setTimeout(1, self.stop)

    def onReconnect(self, room):
        print("Reconnected to "+room.name)

    def onDisconnect(self, room):
        print("Disconnected from "+room.name)

    def onMessage(self, room, user, message):
        self.safePrint(user.name + ': ' + message.body)

        if message.body.startswith("!a"):
            room.message("AAAAAAAAAAAAAA")

    def onFloodBan(self, room):
        print("You are flood banned in "+room.name)

    def onPMMessage(self, pm, user, body):
        self.safePrint('PM: ' + user.name + ': ' + body)
        pm.message(user, body) # echo


def test_run():
    if password := os.environ.get('CHPYBOT_PASSWORD'):
        Bot.easy_start(['chpyroom'], 'chpybot', password)
    else:
        raise EnvironmentError('Password not found in ENV')
