#!/usr/bin/python
from typing import Callable, Optional
import threading
import asyncio
import pytest
import os
import ch
import ch.mixin


class Bot(ch.mixin.WindowsMainLoopFix, ch.RoomManager):
    # Set backward compatibility behavior flag for older bots
    # using threading for non deterministic modification of tasks or conns (rooms)
    disconnectOnEmptyConnAndTask = False


class CallEvent():
    def __init__(self, instance: ch.RoomManager , replacement: Optional[dict[str, Callable[..., None]]] = None):
        self.instance = instance
        self.func = instance._callEvent
        instance._callEvent = self.call
        self.replacement: dict[str, Callable[..., None]] = replacement or dict()

    def setReplacement(self, replacement: dict[str, Callable[..., None]] = None):
        self.replacement = replacement

    def clearReplacement(self):
        self.replacement.clear()

    def call(self, conn: ch.Conn, evt: str, *args: ..., **kw: ...):
        if (func := self.replacement.get(evt)) is not None:
            func(self.instance, conn, *args, **kw)
        else:
            self.func(conn, evt, *args, **kw)

@pytest.mark.timeout(30)
class TestCases():
    @classmethod
    def setup_class(cls):
        cls.config: dict[str, str] = {  # type: ignore
            'username': os.environ.get('CHPYBOT_USER'),
            'password': os.environ.get('CHPYBOT_PASSWORD'),
            'roomname': 'chpyroom'
        }
        if cls.config['username'] and cls.config['password']:
            cls.instance = Bot(cls.config['username'], cls.config['password'])
            cls.CE = CallEvent(cls.instance)
            cls.instance_thread = threading.Thread(target=cls.instance.main, name='bot', daemon=True)
            cls.instance_thread.start()
        else:
            raise EnvironmentError('Password not found in ENV')

    def teardown_method(self, method):
        self.CE.clearReplacement()

    @pytest.mark.asyncio
    async def test_join_and_connect(tst):
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        def onConnect(self, room):
            future.get_loop().call_soon_threadsafe(future.set_result, room.name == tst.config['roomname'])

        tst.CE.setReplacement({'onConnect': onConnect})
        tst.instance.joinRoom(tst.config['roomname'])
 
        assert await future

    @pytest.mark.asyncio
    async def test_message_and_receive(tst):
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        msg = "testing sending and receiving message"

        def onMessage(self, room, user, message):
            results = []
            results.append(self.user == user == message.user)
            results.append(message.body == msg)
            results.append(room.name == tst.config['roomname'] == message.room.name)

            future.get_loop().call_soon_threadsafe(future.set_result, results)

        tst.CE.setReplacement({'onMessage': onMessage})
        if room := tst.instance.getRoom(tst.config['roomname']):
            room.message(msg)
        else:
            raise RuntimeError('Room not found')
 
        assert all(await future)

    @classmethod
    def teardown_class(cls):
        cls.instance.setTimeout(0, cls.instance.stop) 
        cls.instance_thread.join()
