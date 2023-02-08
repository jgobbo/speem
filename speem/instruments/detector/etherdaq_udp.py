from dataclasses import dataclass, field

from scapy.layers.inet import UDP
from scapy.packet import Raw
from scapy.sendrecv import AsyncSniffer
from scapy.config import conf
from scapy.sessions import IPSession

# from scapy.utils import wrpcap

from typing import List, Tuple, Callable
import struct
import bitstruct
import time
from random import randint

from aioprocessing import AioQueue
from asyncio import Queue

# __all__ = ["EtherDAQListener"]


# IFACE = "{963639B6-9ADD-4993-93FA-8B22F38CDFAC}"  # Private LAN for EtherDAQ
IFACE = "{CFB6309D-B51C-4E88-BF1C-211697B1DF5F}"
IFACE_IDX = 4  # Private LAN for EtherDAQ

ETHER_UDP_PORT = 60000
ETHER_UDP_IP = "192.168.0.5"
ETHER_HEADER_LENGTH = 4
ETHER_BODY_OFFSET = 2
ETHER_X_BITS = 14
ETHER_Y_BITS = 14
ETHER_P_BITS = 8
ETHER_T_BITS = 48
EVENT_STRIDE_BYTES = 12

ETHER_FPGA_MAC = "00:0a:35:01:02:03"

# TODO find a unique identifier for the TDC boards which isn't computer specific and doesn't change if the connection is reset (might not be possible)
# TODO get the swapping check figured out

CHECK_XY_RANGE = range(85, 95)
CHECK_QT_RANGE = range(125, 135)


def translate_msg_to_photon_list(
    msg: bytes,
) -> Tuple[int, List[Tuple[int, int, int]], int]:
    header_bytes, msg = (
        msg[:ETHER_HEADER_LENGTH],
        msg[ETHER_HEADER_LENGTH + ETHER_BODY_OFFSET :],
    )
    n_events, packet_id = struct.unpack("<HH", header_bytes)
    n_events //= 2

    events = []
    n_failed = 0
    for i in range(n_events):
        xy_data = msg[EVENT_STRIDE_BYTES * i : EVENT_STRIDE_BYTES * i + 6]
        qt_data = msg[EVENT_STRIDE_BYTES * i + 6 : EVENT_STRIDE_BYTES * i + 12]
        x, y, check_xy = bitstruct.unpack("u16u16u16<", xy_data)
        q, t, check_qt = bitstruct.unpack("u16u16u16<", qt_data)
        # Sometimes xy and qt are swapped so we can check static bytes to see if they need to be swapped back
        if (check_xy in CHECK_XY_RANGE) and (check_qt in CHECK_QT_RANGE):
            events.append((x, y, t))
        elif (check_xy in CHECK_QT_RANGE) and (check_qt in CHECK_XY_RANGE):
            events.append((q, t, y))
        else:
            n_failed += 1

    return packet_id, events, n_failed


def translate_packet_to_photon_list(
    udp_packet,
) -> Tuple[int, List[Tuple[int, int, int]], int]:
    udp_packet = udp_packet[UDP]

    if udp_packet.sport != ETHER_UDP_PORT:
        return None

    return translate_msg_to_photon_list(bytes(udp_packet.payload))


@dataclass
class EtherDAQListener:
    packet_callbacks: List[Callable] = field(default_factory=list)

    # messages: AioQueue = field(default_factory=AioQueue)
    messages: Queue = field(default_factory=Queue)
    sniffer: AsyncSniffer = field(init=False)

    @staticmethod
    def find_appropriate_iface(ip_addr: str, interface: str):
        for iface in conf.ifaces.values():
            if iface.guid == interface:
                return iface
            # if (
            #     ip_addr in iface.ips[4]
            # ):  # this was causing issues with ip mapping (masking?)
            #     return iface

        raise Exception("Etherdaq interface not found.")

    def receive_packet(self, packet):
        if packet.src != ETHER_FPGA_MAC:
            return

        if Raw in packet:
            packet[Raw].load

        packet_id, events, n_failed = translate_packet_to_photon_list(packet)

        # try:
        #     packet_id, events, n_failed = translate_packet_to_photon_list(packet)
        # except Exception as e:
        #     filename = "failed_packet.pcap"
        #     print(f"Caught exception: {e}. Logging packet in {filename}")
        #     wrpcap(filename, packet)
        #     return None

        try:
            # self.messages.put((time.time(), packet_id, events, n_failed))
            self.messages.put_nowait((time.time(), packet_id, events, n_failed))
        except RuntimeError:
            print("Etherdaq data lost by asyncio.")

        for cb in self.packet_callbacks:
            cb(packet_id, events)

    def dummy_packet(self, _packet):
        n_events = randint(50000, 100000)
        packets = []
        for _ in range(n_events):
            packets.append((randint(0, 4095), randint(0, 4095), randint(0, 4095)))
        self.messages.put_nowait((-1, -2, packets, 0))

    def __post_init__(self):
        iface = self.find_appropriate_iface(ETHER_UDP_IP, IFACE)
        self.sniffer = AsyncSniffer(
            filter="udp",
            session=IPSession,
            count=0,
            iface=iface,
            store=False,
            prn=self.receive_packet,  # change to self.dummy_packet to simulate receiving counts
        )

    def on_packet_received(self, packet_callback: Callable):
        self.packet_callbacks.append(packet_callback)

    def start(self):
        self.sniffer.start()

    def stop(self):
        self.sniffer.stop()
