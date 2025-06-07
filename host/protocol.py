from __future__ import annotations
import msgpack, struct
from typing import Any, Callable, TypeVar, IO
from types import MethodType


# struct format characters: https://docs.python.org/3/library/struct.html#format-characters


CMDS_ATTR = "__msghandler_cmds"
T = TypeVar("T", bound="Service")

def msghandler(*cmds: str):
    def decorator(func: Callable[[T, dict[str, Any]], Any]):
        setattr(func, CMDS_ATTR, cmds)
        return func
    return decorator


class Service:
    class ID:
        HOST        = 0
        INFERENCE   = 1

    def __init__(self, protocol: Protocol):
        self.protocol = protocol

        # Register decorated message handlers
        for name, method in self.__class__.__dict__.items():
            if cmds := getattr(method, CMDS_ATTR, None):
                delattr(method, CMDS_ATTR)
                boundMethod = MethodType(method, self)
                for cmd in cmds:
                    self.protocol.setMessageHandler(cmd, boundMethod)



class Protocol:
    HEADER_LENGTH = 10  #  service ID (2), length (4), request ID (4)

    def __init__(self, serviceId: int, bufIn: IO[bytes], bufOut: IO[bytes]):
        self.serviceId = serviceId

        self.bufIn  = bufIn
        self.bufOut = bufOut

        self.services: dict[int, Protocol] = dict()
        self.serviceSpawners: dict[int, Callable[[int], Protocol]] = dict()
        self.msgHandlers: dict[str, Callable[[dict[str, Any]], Any]] = dict()


    def setSubServiceSpawner(self, serviceId: int, spawner: Callable[[int], Protocol]):
        self.serviceSpawners[serviceId] = spawner

    def setSubService(self, serviceId: int, protocol: Protocol):
        self.services[serviceId] = protocol

    def _getSubService(self, serviceId: int) -> Protocol | None:
        if prot := self.services.get(serviceId):
            return prot

        if spawner := self.serviceSpawners.pop(serviceId, None):
            self.services[serviceId] = prot = spawner(serviceId)
            return prot

        return None


    def setMessageHandler(self, cmd: str, handler: Callable[[dict[str, Any]], Any]):
        self.msgHandlers[cmd] = handler

    def handleMessage(self, reqId: int, msg: dict[str, Any]):
        cmd = msg["cmd"]
        handler = self.msgHandlers[cmd]
        # TODO: Run in separate thread if desired
        out = handler(msg)
        if out is not None:
            self.writeMessage(reqId, out)


    def readMessage(self) -> tuple[int, dict[str, Any] | None]:
        header = self.bufIn.read(self.HEADER_LENGTH)
        srv, length, reqId = struct.unpack("!HII", header)
        if srv > 256:
            print(f"WARNING: Protocol received message for service {srv}")

        data = self.bufIn.read(length)

        if srv == self.serviceId:
            return reqId, msgpack.unpackb(data)
        elif prot := self._getSubService(srv):
            prot.writeSubService(reqId, header, data)
        return 0, None


    def writeMessage(self, reqId: int, msg: dict[str, Any]):
        data: bytes = msgpack.packb(msg)
        header: bytes = struct.pack("!HII", self.serviceId, len(data), reqId)
        self.write(header, data)

    def writeSubService(self, reqId: int, header: bytes, data: bytes):
        self.write(header, data)

    def write(self, header: bytes, data: bytes):
        self.bufOut.write(header)
        self.bufOut.write(data)
        self.bufOut.flush()



class MessageLoop:
    def __init__(self, protocol: Protocol):
        self.protocol = protocol
        self.running = True

    def stop(self):
        self.running = False

    def __call__(self):
        import sys, traceback
        while self.running:
            reqId = 0
            try:
                reqId, msg = self.protocol.readMessage()
                if msg is not None:
                    self.protocol.handleMessage(reqId, msg)
            except KeyboardInterrupt:
                self.running = False
            except:
                exType, exMessage, exTraceback = sys.exc_info()
                traceback.print_exc()
                self.handleError(reqId, str(exType), str(exMessage))

    def handleError(self, reqId: int, excType: str, excMessage: str) -> None:
        import re
        pattern = r"<class '([^']+)'>"
        if match := re.match(pattern, excType):
            excType = match.group(1)

        self.protocol.writeMessage(reqId, {
            "error_type": excType,
            "error": excMessage
        })

