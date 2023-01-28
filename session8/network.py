import socket
import time

from io import BytesIO
from random import randint
from unittest import TestCase

from block import Block
from helper import (
    hash256,
    decode_base58,
    encode_varint,
    int_to_little_endian,
    little_endian_to_int,
    read_varint,
)
from tx import Tx

TX_DATA_TYPE = 1
BLOCK_DATA_TYPE = 2
FILTERED_BLOCK_DATA_TYPE = 3
COMPACT_BLOCK_DATA_TYPE = 4

MAGIC = {
    "mainnet": b"\xf9\xbe\xb4\xd9",
    "testnet": b"\x0b\x11\x09\x07",
    "signet": b"\x0a\x03\xcf\x40",
}
PORT = {
    "mainnet": 8333,
    "testnet": 18333,
    "signet": 38333,
}


class NetworkEnvelope:
    def __init__(self, command, payload, network="mainnet"):
        self.command = command
        self.payload = payload
        self.magic = MAGIC[network]

    def __repr__(self):
        return '{self.command.decode("ascii")}: {self.payload.hex()}'

    @classmethod
    def parse(cls, s, network="mainnet"):
        """Takes a stream and creates a NetworkEnvelope"""
        # check the network magic
        magic = s.read(4)
        if magic == b"":
            raise RuntimeError("Connection reset!")
        if magic != MAGIC[network]:
            raise RuntimeError(
                f"magic is not right {magic.hex()} vs {MAGIC[network].hex()}"
            )
        # command 12 bytes, strip the trailing 0's using .strip(b'\x00')
        command = s.read(12).strip(b"\x00")
        # payload length 4 bytes, little endian
        payload_length = little_endian_to_int(s.read(4))
        # checksum 4 bytes, first four of hash256 of payload
        checksum = s.read(4)
        # payload is of length payload_length
        payload = s.read(payload_length)
        # verify checksum
        calculated_checksum = hash256(payload)[:4]
        if calculated_checksum != checksum:
            raise RuntimeError("checksum does not match")
        return cls(command, payload, network=network)

    def serialize(self):
        """Returns the byte serialization of the entire network message"""
        # add the network magic using self.magic
        result = self.magic
        # command 12 bytes, fill leftover with b'\x00' * (12 - len(self.command))
        result += self.command + b"\x00" * (12 - len(self.command))
        # payload length 4 bytes, little endian
        result += int_to_little_endian(len(self.payload), 4)
        # checksum 4 bytes, first four of hash256 of payload
        result += hash256(self.payload)[:4]
        # payload
        result += self.payload
        return result

    def stream(self):
        """Returns a stream for parsing the payload"""
        return BytesIO(self.payload)


class NetworkEnvelopeTest(TestCase):
    def test_parse(self):
        msg = bytes.fromhex("f9beb4d976657261636b000000000000000000005df6e0e2")
        stream = BytesIO(msg)
        envelope = NetworkEnvelope.parse(stream)
        self.assertEqual(envelope.command, b"verack")
        self.assertEqual(envelope.payload, b"")
        msg = bytes.fromhex(
            "f9beb4d976657273696f6e0000000000650000005f1a69d2721101000100000000000000bc8f5e5400000000010000000000000000000000000000000000ffffc61b6409208d010000000000000000000000000000000000ffffcb0071c0208d128035cbc97953f80f2f5361746f7368693a302e392e332fcf05050001"
        )
        stream = BytesIO(msg)
        envelope = NetworkEnvelope.parse(stream)
        self.assertEqual(envelope.command, b"version")
        self.assertEqual(envelope.payload, msg[24:])

    def test_serialize(self):
        msg = bytes.fromhex("f9beb4d976657261636b000000000000000000005df6e0e2")
        stream = BytesIO(msg)
        envelope = NetworkEnvelope.parse(stream)
        self.assertEqual(envelope.serialize(), msg)
        msg = bytes.fromhex(
            "f9beb4d976657273696f6e0000000000650000005f1a69d2721101000100000000000000bc8f5e5400000000010000000000000000000000000000000000ffffc61b6409208d010000000000000000000000000000000000ffffcb0071c0208d128035cbc97953f80f2f5361746f7368693a302e392e332fcf05050001"
        )
        stream = BytesIO(msg)
        envelope = NetworkEnvelope.parse(stream)
        self.assertEqual(envelope.serialize(), msg)


class VersionMessage:
    command = b"version"
    define_network = False

    def __init__(
        self,
        version=70015,
        services=0,
        timestamp=None,
        receiver_services=0,
        receiver_ip=b"\x00\x00\x00\x00",
        receiver_port=8333,
        sender_services=0,
        sender_ip=b"\x00\x00\x00\x00",
        sender_port=8333,
        nonce=None,
        user_agent=b"/programmingblockchain:0.1/",
        latest_block=0,
        relay=True,
    ):
        self.version = version
        self.services = services
        if timestamp is None:
            self.timestamp = int(time.time())
        else:
            self.timestamp = timestamp
        self.receiver_services = receiver_services
        self.receiver_ip = receiver_ip
        self.receiver_port = receiver_port
        self.sender_services = sender_services
        self.sender_ip = sender_ip
        self.sender_port = sender_port
        if nonce is None:
            self.nonce = int_to_little_endian(randint(0, 2**64), 8)
        else:
            self.nonce = nonce
        self.user_agent = user_agent
        self.latest_block = latest_block
        self.relay = relay

    def serialize(self):
        """Serialize this message to send over the network"""
        # version is 4 bytes little endian
        result = int_to_little_endian(self.version, 4)
        # services is 8 bytes little endian
        result += int_to_little_endian(self.services, 8)
        # timestamp is 8 bytes little endian
        result += int_to_little_endian(self.timestamp, 8)
        # receiver services is 8 bytes little endian
        result += int_to_little_endian(self.receiver_services, 8)
        # IPV4 is 10 00 bytes and 2 ff bytes then receiver ip
        result += b"\x00" * 10 + b"\xff\xff" + self.receiver_ip
        # receiver port is 2 bytes, little endian
        result += int_to_little_endian(self.receiver_port, 2)
        # sender services is 8 bytes little endian
        result += int_to_little_endian(self.sender_services, 8)
        # IPV4 is 10 00 bytes and 2 ff bytes then sender ip
        result += b"\x00" * 10 + b"\xff\xff" + self.sender_ip
        # sender port is 2 bytes, little endian
        result += int_to_little_endian(self.sender_port, 2)
        # nonce
        result += self.nonce
        # useragent is a variable string, so varint first
        result += encode_varint(len(self.user_agent))
        result += self.user_agent
        # latest block is 4 bytes little endian
        result += int_to_little_endian(self.latest_block, 4)
        # relay is 00 if false, 01 if true
        if self.relay:
            result += b"\x01"
        else:
            result += b"\x00"
        return result


class VersionMessageTest(TestCase):
    def test_serialize(self):
        v = VersionMessage(timestamp=0, nonce=b"\x00" * 8)
        self.assertEqual(
            v.serialize().hex(),
            "7f11010000000000000000000000000000000000000000000000000000000000000000000000ffff000000008d20000000000000000000000000000000000000ffff000000008d2000000000000000001b2f70726f6772616d6d696e67626c6f636b636861696e3a302e312f0000000001",
        )


class VerAckMessage:
    command = b"verack"
    define_network = False

    def __init__(self):
        pass

    @classmethod
    def parse(cls, s):
        return cls()

    def serialize(self):
        return b""


class PingMessage:
    command = b"ping"
    define_network = False

    def __init__(self, nonce):
        self.nonce = nonce

    @classmethod
    def parse(cls, s):
        nonce = s.read(8)
        return cls(nonce)

    def serialize(self):
        return self.nonce


class PongMessage:
    command = b"pong"
    define_network = False

    def __init__(self, nonce):
        self.nonce = nonce

    def parse(cls, s):
        nonce = s.read(8)
        return cls(nonce)

    def serialize(self):
        return self.nonce


class GetHeadersMessage:
    command = b"getheaders"
    define_network = False

    def __init__(self, version=70015, num_hashes=1, start_block=None, end_block=None):
        self.version = version
        self.num_hashes = num_hashes
        if start_block is None:
            raise RuntimeError("a start block is required")
        self.start_block = start_block
        if end_block is None:
            self.end_block = b"\x00" * 32
        else:
            self.end_block = end_block

    def serialize(self):
        """Serialize this message to send over the network"""
        # protocol version is 4 bytes little-endian
        result = int_to_little_endian(self.version, 4)
        # number of hashes is a varint
        result += encode_varint(self.num_hashes)
        # start block is in little-endian
        result += self.start_block[::-1]
        # end block is also in little-endian
        result += self.end_block[::-1]
        return result


class GetHeadersMessageTest(TestCase):
    def test_serialize(self):
        block_hex = "0000000000000000001237f46acddf58578a37e213d2a6edc4884a2fcad05ba3"
        gh = GetHeadersMessage(start_block=bytes.fromhex(block_hex))
        self.assertEqual(
            gh.serialize().hex(),
            "7f11010001a35bd0ca2f4a88c4eda6d213e2378a5758dfcd6af437120000000000000000000000000000000000000000000000000000000000000000000000000000000000",
        )


class HeadersMessage:
    command = b"headers"
    define_network = False

    def __init__(self, headers):
        self.headers = headers

    def __iter__(self):
        for header in self.headers:
            yield header

    @classmethod
    def parse(cls, s):
        # number of headers is in a varint
        num_headers = read_varint(s)
        # initialize the headers array
        headers = []
        # loop through number of headers times
        for _ in range(num_headers):
            # parse a header using Block.parse(s)
            header = Block.parse(s)
            # add the header to the headers array
            headers.append(header)
            # check that the length of header.tx_hashes to be 0 or raise a RuntimeError
            if len(header.tx_hashes) != 0:
                raise RuntimeError("number of txs not 0")
        # return a class instance
        return cls(headers)

    def is_valid(self):
        """Return whether the headers satisfy proof-of-work and are sequential and have the correct bits"""
        last_block = None
        for h in self.headers:
            if not h.check_pow():
                return False
            if last_block and h.prev_block != last_block:
                return False
            last_block = h.hash()
        return True


class HeadersMessageTest(TestCase):
    def test_parse(self):
        hex_msg = "0200000020df3b053dc46f162a9b00c7f0d5124e2676d47bbe7c5d0793a500000000000000ef445fef2ed495c275892206ca533e7411907971013ab83e3b47bd0d692d14d4dc7c835b67d8001ac157e670000000002030eb2540c41025690160a1014c577061596e32e426b712c7ca00000000000000768b89f07044e6130ead292a3f51951adbd2202df447d98789339937fd006bd44880835b67d8001ade09204600"
        stream = BytesIO(bytes.fromhex(hex_msg))
        headers = HeadersMessage.parse(stream)
        self.assertEqual(len(headers.headers), 2)
        for b in headers.headers:
            self.assertEqual(b.__class__, Block)


class GetDataMessage:
    command = b"getdata"
    define_network = False

    def __init__(self):
        self.data = []

    def add_data(self, data_type, identifier):
        self.data.append((data_type, identifier))

    def serialize(self):
        # start with the number of items as a varint
        result = encode_varint(len(self.data))
        # loop through self.data which is a list of data_type and identifier
        for data_type, identifier in self.data:
            # data type is 4 bytes little endian
            result += int_to_little_endian(data_type, 4)
            # identifier needs to be in little endian
            result += identifier[::-1]
        # return the whole thing
        return result


class GetDataMessageTest(TestCase):
    def test_serialize(self):
        hex_msg = "020300000030eb2540c41025690160a1014c577061596e32e426b712c7ca00000000000000030000001049847939585b0652fba793661c361223446b6fc41089b8be00000000000000"
        get_data = GetDataMessage()
        block1 = bytes.fromhex(
            "00000000000000cac712b726e4326e596170574c01a16001692510c44025eb30"
        )
        get_data.add_data(FILTERED_BLOCK_DATA_TYPE, block1)
        block2 = bytes.fromhex(
            "00000000000000beb88910c46f6b442312361c6693a7fb52065b583979844910"
        )
        get_data.add_data(FILTERED_BLOCK_DATA_TYPE, block2)
        self.assertEqual(get_data.serialize().hex(), hex_msg)


class GenericMessage:
    define_network = False

    def __init__(self, command, payload):
        self.command = command
        self.payload = payload

    def serialize(self):
        return self.payload


class SimpleNode:
    def __init__(self, host, port=None, network="mainnet", logging=False):
        if port is None:
            port = PORT[network]
        self.network = network
        self.logging = logging
        # connect to socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((host, port))
        # create a stream that we can use with the rest of the library
        self.stream = self.socket.makefile("rb", None)

    def handshake(self):
        """Do a handshake with the other node. Handshake is sending a version message and getting a verack back."""
        # create a version message
        version = VersionMessage()
        # send the command
        self.send(version)
        # wait for a verack message
        self.wait_for(VerAckMessage)

    def send(self, message):
        """Send a message to the connected node"""
        # create a network envelope
        envelope = NetworkEnvelope(
            message.command, message.serialize(), network=self.network
        )
        if self.logging:
            print(f"sending: {envelope}")
        # send the serialized envelope over the socket using sendall
        self.socket.sendall(envelope.serialize())

    def read(self):
        """Read a message from the socket"""
        envelope = NetworkEnvelope.parse(self.stream, network=self.network)
        if self.logging:
            print(f"receiving: {envelope}")
        return envelope

    def wait_for(self, *message_classes):
        """Wait for one of the messages in the list"""
        # initialize the command we have, which should be None
        command = None
        command_to_class = {m.command: m for m in message_classes}
        # loop until the command is in the commands we want
        while command not in command_to_class.keys():
            # get the next network message
            envelope = self.read()
            # set the command to be evaluated
            command = envelope.command
            # we know how to respond to version and ping, handle that here
            if command == VersionMessage.command:
                # send verack
                self.send(VerAckMessage())
            elif command == PingMessage.command:
                # send pong
                self.send(PongMessage(envelope.payload))
        # return the envelope parsed as a member of the right message class
        cls = command_to_class[command]
        if cls.define_network:
            return cls.parse(envelope.stream(), network=self.network)
        else:
            return cls.parse(envelope.stream())

    def is_tx_accepted(self, tx_obj):
        """Returns whether a transaction has been accepted on the network"""
        # create a GetDataMessage
        get_data = GetDataMessage()
        # ask for the tx
        get_data.add_data(TX_DATA_TYPE, tx_obj.hash())
        # send the GetDataMessage
        self.send(get_data)
        # now wait for a response
        got_tx = self.wait_for(Tx)
        if got_tx.id() == tx_obj.id():
            return True

    def get_block(self, block_hash):
        # create a GetDataMessage
        # to the message, run the method add_data(BLOCK_DATA_TYPE, block_hash)
        # send the message
        # wait for the Block message and store it as a block object
        # check that the block hash is what we expect
        # return the block object
        raise NotImplementedError


class SimpleNodeTest(TestCase):
    def test_handshake(self):
        node = SimpleNode("signet.programmingbitcoin.com", network="signet")
        node.handshake()

    def test_get_block(self):
        node = SimpleNode("testnet.programmingbitcoin.com", network="testnet")
        node.handshake()
        want = "00000000b4a283fd078500ef347c1646985261f925a4d4b67c143cc1ba2a3b57"
        b = node.get_block(bytes.fromhex(want))
        self.assertEqual(b.hash().hex(), want)