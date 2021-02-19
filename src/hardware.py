from math import ceil
from time import sleep

import board
import digitalio
import busio

# Constants:
UART_NUM = 1
BAUD_RATE = 9600
TX_PIN = 8
RX_PIN = 9
TX_EN_PIN = 15
ONE_FRAME = 10 / BAUD_RATE * 1000.0
TWO_FRAMES = int(ceil(10 / BAUD_RATE * 1000.0))
BACKOFF_TIME = (0.001, 0.005)
STATUS_RED = 27
STATUS_GREEN = 28
TIMER_ADDR = 0x0000

MODE_SLEEP = 0
MODE_READY = 1
MODE_ARMED = 2
MODE_DISARMED = 3

MT_REQUEST_ID = 0
MT_RESPONSE_ID = 1
MT_ACK = 2
MT_STOP = 3
MT_CONFIGURE = 4
MT_START = 5
MT_STRIKE = 6
MT_ERROR = 7
MT_DEFUSED = 8
MT_NEEDY = 9
MT_READ_STATUS = 10
MT_STATUS = 11
MT_SOUND = 12

FLAG_TRIGGER = 0x01
FLAG_NEEDY = 0x02
FLAG_EXCLUSIVE = 0x04

SOUND_HALT = 0
SOUND_SIMON_1 = 1
SOUND_SIMON_2 = 2
SOUND_SIMON_3 = 3
SOUND_SIMON_4 = 4
SOUND_TIMER_LOW = 5
SOUND_BUTTON_1 = 6
SOUND_BUTTON_2 = 7
SOUND_TUNE_UP = 8
SOUND_TUNE_DOWN = 9
SOUND_VENT = 10
SOUND_START_CAP_1 = 11
SOUND_START_CAP_2 = 12
SOUND_START_CAP_3 = 13
SOUND_START_CAP_4 = 14
SOUND_MORSE_A = 15
SOUND_MORSE_Z = 40


class KtaneHardware:
    def __init__(self, addr: int) -> None:
        self.handlers = {}
        self.queued_packet = None
        self.next_retry = None
        self.last_seq_seen = None

    # UART MEMBERS
    #
    # Packet format (little-endian fields):
    #
    # Field      Length     Notes
    # -------    --------   ----------------------------------------------------
    # Length     1          Total packet length not including Length or Checksum
    # Source     2          Packet source address
    # Dest       2          Packet destination address
    # Type       1          Message type
    # SeqNum     1          Sequence number
    # Payload    variable   Content depends on message type
    # Checksum   2          Checksum such that when all bytes of the message (including Checksum) are summed, the total
    #                       will be 0xFFFF
    def poll(self) -> None:
        """Poll UART"""
        with digitalio.DigitalInOut(board.RX) as rx:
            rx.pull = digitalio.Pull.DOWN

            if rx.value == False:  # there is nothing to read
                return

            while rx.value == True:
                pass

            print("Detected pulldown, reading message: ", end="")

        with busio.UART(board.TX, board.RX, baudrate=BAUD_RATE, timeout=1) as uart:
            length = uart.read(1)[0]  # read length byte
            print(length)
            data = uart.read(length + 2)  # read data + checksum
            if data is not None:
                # convert bytearray to string
                data_string = (
                    ", ".join([str(b) for b in data[:-2]]) + "  cs: " + str(data[-2:])
                )
                print(data)

    def send(
        self, dest: int, packet_type: int, seq_num: int, payload: bytes = b""
    ) -> None:
        """Send a packet"""
        # Is anything inbound?
        with digitalio.DigitalInOut(board.RX) as rx:
            rx.pull = digitalio.Pull.UP

            while rx.value == True:
                self.poll()
                sleep(randrange(*BACKOFF_TIME))

        # Send packet
        data = (
            struct.pack(
                "<BHHBB",
                2 + 2 + 1 + 1 + len(payload),
                self.addr,
                dest,
                packet_type,
                seq_num,
            )
            + payload
        )
        data += struct.pack("<H", 0xFFFF - sum(data))

        with digitalio.DigitalInOut(board.TX) as tx:
            tx.direction = digitalio.Direction.OUTPUT
            tx.value = True
            sleep(0.1)  # @todo how often can we poll? how often should we?

        with busio.UART(board.TX, board.RX, baudrate=BAUD_RATE, timeout=1) as uart:
            uart.write(data)

        with digitalio.DigitalInOut(board.TX) as tx:
            tx.direction = digitalio.Direction.OUTPUT
            tx.value = False

    def retry_now(self) -> None:
        seq_num = (self.last_seq_seen + 1) & 0xFF
        self.last_seq_seen = self.awaiting_ack_of_seq = seq_num
        self.send(
            self.queued_packet.dest,
            self.queued_packet.packet_type,
            seq_num,
            self.queued_packet.payload,
        )
        self.next_retry = time() + RETRY_TIME

    def queue_packet(self, packet: QueuedPacket) -> None:
        self.queued_packet = packet
        self.retry_now()

    def send_ack(self, dest: int, seq_num: int) -> None:
        self.send(dest, MT_ACK, seq_num)

    def unable_to_arm(self) -> None:
        self.queue_packet(QueuedPacket(TIMER_ADDR, MT_ERROR))

    def disarmed(self):
        self.queue_packet(QueuedPacket(TIMER_ADDR, MT_DEFUSED))
        self.set_mode(MODE_DISARMED)

    def strike(self):
        self.queue_packet(QueuedPacket(TIMER_ADDR, MT_STRIKE))


class QueuedPacket:
    def __init__(self, dest: int, packet_type: int, payload: bytes = b"") -> None:
        self.dest, self.packet_type, self.payload = dest, packet_type, payload