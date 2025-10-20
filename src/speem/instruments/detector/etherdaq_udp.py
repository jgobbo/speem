from dataclasses import dataclass, field
import numpy as np

from scapy.layers.inet import UDP
from scapy.packet import Raw
from scapy.sendrecv import AsyncSniffer
from scapy.config import conf
from scapy.sessions import IPSession

from typing import Callable
import struct
import cbitstruct
from random import randint

from asyncio import Queue

__all__ = ["EtherDAQListener"]


IFACE = "{CFB6309D-B51C-4E88-BF1C-211697B1DF5F}"
IFACE_IDX = 4  # Private LAN for EtherDAQ

ETHER_UDP_PORT = 60000
ETHER_UDP_IP = "192.168.0.5"
ETHER_HEADER_LENGTH = 4
ETHER_BODY_OFFSET = 2
EVENT_STRIDE_BYTES = 12

ETHER_FPGA_MAC = "00:0a:35:01:02:03"

CHECK_XY_RANGE = range(85, 95)
CHECK_QT_RANGE = range(125, 135)


def translate_msg_to_photon_list(msg: bytes) -> np.ndarray:
    header_bytes, msg = (
        msg[:ETHER_HEADER_LENGTH],
        msg[ETHER_HEADER_LENGTH + ETHER_BODY_OFFSET :],
    )
    n_events, _packet_id = struct.unpack("<HH", header_bytes)
    n_events //= 2

    event_data = msg[0 : EVENT_STRIDE_BYTES * n_events]
    all_data = np.array(cbitstruct.unpack(f"{'u16'*6*n_events}<", event_data))
    all_data = all_data.reshape(n_events, 6)

    if all_data.size == 0:
        return np.ndarray(shape=(0, 3), dtype=int)
    elif all_data[0, 3] == 0:
        return all_data[:, [0, 1, 4]]
    else:
        return all_data[:, [3, 4, 1]]


def translate_packet_to_photon_list(
    udp_packet,
) -> np.ndarray:
    udp_packet = udp_packet[UDP]

    if udp_packet.sport != ETHER_UDP_PORT:
        return None

    return translate_msg_to_photon_list(bytes(udp_packet.payload))


@dataclass
class EtherDAQListener:
    packet_callbacks: list[Callable] = field(default_factory=list)

    messages: Queue = field(default_factory=Queue)
    sniffer: AsyncSniffer = field(init=False)

    @staticmethod
    def find_appropriate_iface(ip_addr: str, interface: str):
        for iface in conf.ifaces.values():
            if iface.guid == interface:
                return iface

        raise Exception("Etherdaq interface not found.")

    def receive_packet(self, packet):
        if packet.src != ETHER_FPGA_MAC:
            return

        if Raw in packet:
            packet[Raw].load

        events = translate_packet_to_photon_list(packet)

        # try:
        #     packet_id, events, n_failed = translate_packet_to_photon_list(packet)
        # except Exception as e:
        #     from scapy.utils import wrpcap
        #     filename = "failed_packet.pcap"
        #     print(f"Caught exception: {e}. Logging packet in {filename}")
        #     wrpcap(filename, packet)
        #     return None

        try:
            self.messages.put_nowait(events)
        except RuntimeError:
            print("Etherdaq data lost by asyncio.")

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

    def start(self):
        self.sniffer.start()

    def stop(self):
        self.sniffer.stop()
