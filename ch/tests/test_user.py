#!/usr/bin/python
from typing import Any, Callable, Optional
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
        self.future: asyncio.Future[Any]
        self.fatal_error = False
        self.called_replacement: dict[str, Any] = dict()

    def run_instance(self):
        try:
            self.instance.main()
        except Exception as e:
            self.fatal_error = True
            self.setFutureResult(e)

    def setFutureResult(self, item: Any):
        self.future.get_loop().call_soon_threadsafe(self.future.set_result, item)

    def resetFuture(self):
        loop = asyncio.get_event_loop()
        self.future = loop.create_future()

    async def checkSuccess(self):
        results, error = await self.future
        if error:
            raise error

        return results

    def setReplacement(self, replacement: dict[str, Callable[..., None]] = None):
        self.replacement = replacement
        self.called_replacement.clear()
        self.resetFuture()

    def clearReplacement(self):
        self.replacement.clear()
        self.called_replacement.clear()

    def call(self, conn: ch.Conn, evt: str, *args: ..., **kw: ...):
        """
        If replacement function exists, call it and store the result.

        Resolve the future when all replacement is called once or if an error was encountered.
        """
        if (func := self.replacement.get(evt)) is not None:
            try:
                self.called_replacement[evt] = func(self.instance, conn, *args, **kw)
            except Exception as e:
                self.setFutureResult((self.called_replacement, e))
            if len(self.called_replacement) == len(self.replacement):
                self.setFutureResult((self.called_replacement, None))
        else:
            self.func(conn, evt, *args, **kw)

@pytest.mark.timeout(30)
class TestCases():
    @classmethod
    def setup_class(cls):
        cls.config: dict[str, str] = {  # type: ignore
            'username': os.environ.get('CHPYBOT_USER'),
            'password': os.environ.get('CHPYBOT_PASSWORD'),
            'roomname': os.environ.get('CHPYBOT_ROOM')
        }
        if cls.config['username'] and cls.config['password']:
            cls.instance = Bot(cls.config['username'], cls.config['password'])
            cls.CE = CallEvent(cls.instance)
            cls.instance_thread = threading.Thread(target=cls.CE.run_instance, name='bot', daemon=True)
            cls.instance_thread.start()
        else:
            raise EnvironmentError('Password not found in ENV')

    def setup_method(self, method):
        ...

    def teardown_method(self, method):
        self.CE.clearReplacement()

        if self.CE.fatal_error:
            pytest.exit('fatal error encountered, bot thread stopped')

    @pytest.mark.asyncio
    async def test_exception_returnable(tst):
        class testException(Exception):
            pass

        def onTest(self, room):
            return testException()

        tst.CE.setReplacement({'onTest': onTest})
        tst.instance.setTimeout(0, lambda: tst.instance._callEvent(None, 'onTest'))

        results = await tst.CE.checkSuccess()
        assert isinstance(results['onTest'], testException)

    @pytest.mark.asyncio
    async def test_exception_error(tst):
        class testException(Exception):
            pass

        def onTest(self, room):
            raise testException()

        tst.CE.setReplacement({'onTest': onTest})
        tst.instance.setTimeout(0, lambda: tst.instance._callEvent(None, 'onTest'))
        with pytest.raises(testException):
            await tst.CE.checkSuccess()

    @pytest.mark.asyncio
    async def test_join_and_connect(tst):
        def onConnect(self, room):
            assert room.name == tst.config['roomname']

        tst.CE.setReplacement({'onConnect': onConnect})
        tst.instance.joinRoom(tst.config['roomname'])
 
        await tst.CE.checkSuccess()

    @pytest.mark.asyncio
    async def test_message_and_receive(tst):
        msg = "testing sending and receiving message"

        def onMessage(self, room, user, message):
            assert self.user == user == message.user
            assert message.body == msg
            assert room.name == tst.config['roomname'] == message.room.name

        tst.CE.setReplacement({'onMessage': onMessage})
        if room := tst.instance.getRoom(tst.config['roomname']):
            room.message(msg)
        else:
            raise RuntimeError('Room not found')
 
        await tst.CE.checkSuccess()

    def test_check_room_owner(tst):
        if room := tst.instance.getRoom(tst.config['roomname']):
            assert room.ownername == tst.instance.user.name == tst.instance.name
            assert room.owner == tst.instance.user
        else:
            raise RuntimeError('Room not found')

    @classmethod
    def teardown_class(cls):
        cls.instance.setTimeout(0, cls.instance.stop) 
        cls.instance_thread.join()
