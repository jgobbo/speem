from dataclasses import dataclass
from enum import IntEnum
import math
from loguru import logger
from modbus_tk.defines import (
    READ_HOLDING_REGISTERS,
    WRITE_SINGLE_REGISTER,
    WRITE_MULTIPLE_REGISTERS,
    READ_WRITE_MULTIPLE_REGISTERS,
)
from modbus_tk.modbus_tcp import TcpMaster
from modbus_tk.exceptions import ModbusError


__all__ = [
    "RudiHV",
    "RudiDAC",
]

IP_ADDRESS = "192.168.202.2"
BYTE = 1
WORD = 2
VOLTS_TO_MILLIVOLTS = 10**3
VOLTS_TO_MICROVOLTS = 10**6


def hex_tc(value: int, n_bits: int = 32):
    """
    Returns the two's complement hex value
    """
    return hex((value + (1 << n_bits)) % (1 << n_bits))


def data_to_integer(data: list[int], n_bits: int = 32) -> int:
    """
    Converts the 16 bit separated integer values into a single integer
    """
    dataL = data[0] << (n_bits // 2)
    dataLR = dataL | data[1]
    if (dataLR >> (n_bits - 1)) == 1:
        dataLR = dataLR - (2**n_bits)
    return dataLR


# def dataToSignedNumber(data):
#     dataL = data[0] << 15
#     dataLR = dataL | data[1]
#     unsigned = dataLR % 2 ** 16
#     signed = unsigned - 2 ** 16 if unsigned >= 2 ** 15 else unsigned
#     return signed * (10 ** (-3))


def version_convert(version: int) -> tuple[str, str]:
    """
    Converts a raw version number into a hardware and firmware string
    Note: I (Jacob) changed the code so it might be wrong now. It didn't
    make any sense before so...
    """
    hardware_bits = bin(version)[2:-5]
    hardware = str(int(hardware_bits, 2))
    hardware_string = f"{hardware[0]}.{hardware[1]}.{hardware[2:]}"

    firmware_bits = bin(version)[-5:]
    firmware_string = str(int(firmware_bits, 2))

    return hardware_string, firmware_string


def calibration_check(points: list[int]) -> bool:
    """
    The method checks the card calibrations. The card is not calibrated when
    appears more than one point with an absolute value 65535.

    :param points: List of digital points e.g. [dig_Point0, dig_Point_1]
    :return: 1-is calibrated, 0-is not calibrated
    """
    dig_ = [1 if abs(x[0]) == 65535 else 0 for x in points]
    return dig_.count(1) <= 1


def truncate(number, digits) -> float:
    stepper = pow(10.0, digits)
    return math.trunc(stepper * number) / stepper


class FloatRange:
    def __init__(self, min, max) -> None:
        if min < max:
            self.min = min
            self.max = max
        else:
            self.min = max
            self.max = min

    def __contains__(self, value):
        return self.min <= value <= self.max

    def __str__(self) -> str:
        return f"({self.min}, {self.max})"

    def clamp(self, number: float):
        if number < self.min:
            return self.min
        elif number > self.max:
            return self.max
        else:
            return number


class OutOfRangeError(Exception):
    """Exception for Rudi modules when a desired voltage is out of range."""


class HVMode(IntEnum):
    TRANSPARENT = 2
    POSITIVE_HIGH = 3
    NEGATIVE_HIGH = 4
    POSITIVE_LOW = 5
    NEGATIVE_LOW = 6
    SHORT_OUTPUT = 7

    def __str__(self) -> str:
        return {
            2: "DAC",
            3: "Positive High",
            4: "Negative High",
            5: "Positive Low",
            6: "Negative Low",
            7: "Short Output",
        }[self.value]


DEFAULT_RANGES = {
    1: (FloatRange(2.986, 600.0), FloatRange(4.953, 6000.0)),
    2: (FloatRange(2.994, 600.0), FloatRange(4.903, 6000.0)),
    3: (None, FloatRange(1.991, 600.0)),
    4: (FloatRange(0.499, 100.0), FloatRange(1.999, 600.0)),
    5: (FloatRange(0.499, 100.0), FloatRange(2.0, 600.0)),
    6: (FloatRange(0.499, 100.0), FloatRange(1.999, 600.0)),
    7: (FloatRange(0.496, 100.0), FloatRange(1.988, 600.0)),
    8: (FloatRange(0.499, 100.0), FloatRange(1.999, 600.0)),
    9: (FloatRange(0.499, 100.0), FloatRange(1.994, 600.0)),
    10: (FloatRange(0.5, 100.0), FloatRange(1.995, 600.0)),
    11: (FloatRange(0.5, 100.0), FloatRange(1.994, 600.0)),
    12: (FloatRange(0.5, 100.0), FloatRange(1.994, 600.0)),
    13: (FloatRange(0.5, 100.0), FloatRange(1.993, 600.0)),
    14: (FloatRange(0.499, 100.0), FloatRange(1.996, 600.0)),
    15: (FloatRange(0.5, 100.0), FloatRange(1.994, 600.0)),
    16: (FloatRange(0.499, 100.0), FloatRange(1.998, 600.0)),
}


@dataclass
class HVAddress:
    """
    Map of addresses of HV card registers
    that are queried using the ModbusTCP protocol.
    """

    SETPOINT_BINARY = 0  # R/W
    SETPOINT_mV = 2  # R/W
    OPERATE = 4  # R/W
    WORKING_MODE = 5  # R/W
    STATUS = 6  # R/W
    VOLTAGE = 7  # R
    CARD_VERSION = 9  # R
    N_CAL_POINTS = 10  # R
    SECURITY_WORD = 11  # R
    VOLTAGE_RANGE = 12  # R
    SHORT_CIRCUIT_COUNTER = 14  # R/W
    CAL_POINT_BINARY_START = 16  # R
    CAL_POINT_mV_START = 18  # R
    CAL_POINT_OFFSET = 4


@dataclass
class RudiHV:
    module_address: int
    rudi_ip_address: str = IP_ADDRESS
    addresses = HVAddress
    states_map = {
        0: "After Reset",
        1: "Dual-band card",
        2: "Operate",
        3: "Output fail",
        4: "Output short",
        5: "Low Calib Fail",
        6: "High Calib Fail",
        7: "mV Mode",
    }  # Available card states, which are encoded in the register in the form of an 8-bit map.
    master: TcpMaster = None
    is_dual_channel: bool = None
    high_range: FloatRange = None
    low_range: FloatRange = None
    min_output: float = 0.0
    mode: HVMode = None
    shorted_on_startup: bool = None

    def __post_init__(self):
        self.master = TcpMaster(self.rudi_ip_address, timeout_in_sec=0.5)

        status = self.get_status()
        self.is_dual_channel = status & 0b01000000 != 0

        self.mode = self.get_mode()
        if self.mode is HVMode.SHORT_OUTPUT:
            self.shorted_on_startup = True
            self.get_ranges()
        else:
            self.shorted_on_startup = False
            self.low_range, self.high_range = DEFAULT_RANGES[self.module_address]

    def get_ranges(self):
        self.set_mode(HVMode.POSITIVE_HIGH)
        self.high_range = FloatRange(self.get_min(), self.get_max())
        self.min_output = self.high_range.min
        if self.is_dual_channel:
            self.set_mode(HVMode.POSITIVE_LOW)
            self.low_range = FloatRange(self.get_min(), self.get_max())
            self.min_output = self.low_range.min

        self.set_mode(HVMode.SHORT_OUTPUT)

    def get_voltage(self) -> float:
        if self.mode is HVMode.SHORT_OUTPUT:
            return 0

        data = self.master.execute(
            self.module_address,
            READ_HOLDING_REGISTERS,
            self.addresses.VOLTAGE,
            WORD,
        )
        voltage = data_to_integer(data) / VOLTS_TO_MILLIVOLTS
        return (
            voltage
            if self.mode in {HVMode.POSITIVE_HIGH, HVMode.POSITIVE_LOW}
            else -voltage
        )

    def get_setpoint(self) -> float:
        data = self.master.execute(
            self.module_address,
            READ_HOLDING_REGISTERS,
            self.addresses.SETPOINT_mV,
            WORD,
        )
        voltage = data_to_integer(data) / VOLTS_TO_MILLIVOLTS
        return voltage

    def set_setpoint(self, voltage: float) -> None:
        # print(f"{self.module_address} : {voltage}")

        if voltage == 0:
            return self.set_mode(HVMode.SHORT_OUTPUT)

        is_positive = voltage > 0
        voltage = abs(voltage)

        if self.is_dual_channel and voltage in self.low_range:
            self.set_mode(HVMode.POSITIVE_LOW if is_positive else HVMode.NEGATIVE_LOW)
            return self._set_setpoint(voltage)
        elif voltage in self.high_range:
            self.set_mode(HVMode.POSITIVE_HIGH if is_positive else HVMode.NEGATIVE_HIGH)
            return self._set_setpoint(voltage)

        coerced_voltage = (
            self.high_range.clamp(voltage)
            if is_positive
            else -self.high_range.clamp(voltage)
        )
        logger.warning(
            f"{voltage} is outside of module {self.module_address}'s ranges: {self.low_range}, {self.high_range}. Outputting {coerced_voltage} instead."
        )
        return self.set_setpoint(coerced_voltage)

    def _set_setpoint(self, voltage: float) -> None:
        data = hex(int(voltage * VOLTS_TO_MILLIVOLTS))[2:].zfill(8)
        try:
            self.master.execute(
                slave=self.module_address,
                function_code=READ_WRITE_MULTIPLE_REGISTERS,
                starting_address=self.addresses.SETPOINT_mV,
                quantity_of_x=WORD,
                output_value=[int(data[:4], 16), int(data[4:], 16)],
                expected_length=WORD,
                write_starting_address_FC23=self.addresses.SETPOINT_mV,
            )
        except ModbusError:
            print(
                f"module {self.module_address} failed to output {voltage} in mode {self.mode}."
            )

    def set_mode(self, mode: HVMode) -> None:
        if mode is not self.mode:
            self.mode = mode
            self.master.execute(
                self.module_address,
                WRITE_SINGLE_REGISTER,
                self.addresses.WORKING_MODE,
                output_value=self.mode,
            )

    def get_mode(self) -> HVMode:
        return HVMode(
            self.master.execute(
                self.module_address,
                READ_HOLDING_REGISTERS,
                self.addresses.WORKING_MODE,
                WORD,
            )[0]
        )

    def get_max(self) -> float:
        data = self.master.execute(
            self.module_address,
            READ_HOLDING_REGISTERS,
            self.addresses.VOLTAGE_RANGE,
            WORD,
        )
        return data_to_integer(data) / VOLTS_TO_MILLIVOLTS

    def get_min(self) -> float:
        data = self.master.execute(
            self.module_address,
            READ_HOLDING_REGISTERS,
            self.addresses.CAL_POINT_mV_START,
            WORD,
        )
        return data_to_integer(data) / VOLTS_TO_MILLIVOLTS

    def get_status(self):
        return self.master.execute(
            self.module_address,
            READ_HOLDING_REGISTERS,
            self.addresses.STATUS,
            BYTE,
        )[0]

    def get_version(self):
        data = self.master.execute(
            self.module_address,
            READ_HOLDING_REGISTERS,
            self.addresses.CARD_VERSION,
            WORD,
        )
        return version_convert(data[0])

    def show_info(self):
        card_version = self.get_version()
        voltage = self.get_voltage()
        setpoint = self.get_setpoint()
        max = self.get_max()
        min = self.get_min()
        mode = self.get_mode()
        status = format(self.get_status(), "08b")

        print(f"IP: {self.rudi_ip_address}, DeviceID: {self.module_address}")
        print(
            f"Hardware version: {card_version[0]}, Firmware version: {card_version[1]}"
        )
        print(f"Voltage: {voltage:.3f} [V], Setpoint: {setpoint:.3f} [V]")
        print(f"Mode: {mode}")
        print(f"Range: {min:.3f} - {max:.1f} [V]")
        print(f"Status: {status}")

        print("The HV Card is:")
        [print(f" - {self.states_map[k]}") for k, v in enumerate(status) if v == "1"]


@dataclass
class DACAddress:
    """
    Map of addresses of DAC card registers
    that are queried using the ModbusTCP protocol.
    """

    SETPOINT_BINARY = 0  # R/W
    SETPOINT_uV = 2  # R/W
    STATUS = 4  # R/W
    CARD_VERSION = 5  # R
    N_CAL_POINTS = 6  # R
    SECURITY_WORD = 7  # R
    CAL_POINT_BINARY_START = 8  # R
    CAL_POINT_uV_START = 10  # R
    CAL_POINT_OFFSET = 4


@dataclass
class RudiDAC:
    module_address: int
    rudi_ip_address: str = IP_ADDRESS
    addresses = DACAddress
    states_map = {
        0: "After Reset",
        1: "Calibration Fail",
        2: "uV Mode",
    }  # 3 bit encoding from status value to DAC state
    master: TcpMaster = None
    range = FloatRange(-12, 12)
    min_output = 0.0

    def __post_init__(self):
        self.master = TcpMaster(self.rudi_ip_address, timeout_in_sec=0.1)

    def get_voltage(self) -> float:
        data = self.master.execute(
            self.module_address,
            READ_HOLDING_REGISTERS,
            self.addresses.SETPOINT_uV,
            WORD,
        )
        voltage = data_to_integer(data)
        return voltage / VOLTS_TO_MICROVOLTS

    def set_setpoint(self, voltage: float) -> None:
        # print(f"{self.module_address} : {voltage}")

        if voltage in self.range:
            return self._set_setpoint(voltage)

        raise OutOfRangeError(
            f"Desired output voltage: {voltage} is outside of module {self.module_address}'s range: {self.range}."
        )

    def _set_setpoint(self, voltage: float) -> None:
        data = hex_tc(int(voltage * VOLTS_TO_MICROVOLTS))[2:].zfill(8)
        self.master.execute(
            slave=self.module_address,
            function_code=WRITE_MULTIPLE_REGISTERS,
            starting_address=self.addresses.SETPOINT_uV,
            quantity_of_x=WORD,
            output_value=[int(data[:4], 16), int(data[4:], 16)],
            expected_length=WORD,
            write_starting_address_FC23=self.addresses.SETPOINT_uV,
        )

    def get_status(self):
        return self.master.execute(
            self.module_address,
            READ_HOLDING_REGISTERS,
            self.addresses.STATUS,
            BYTE,
        )[0]

    def get_version(self):
        data = self.master.execute(
            self.module_address,
            READ_HOLDING_REGISTERS,
            self.addresses.CARD_VERSION,
            WORD,
        )
        return version_convert(data[0])

    def show_info(self):
        card_version = self.get_version()
        voltage = self.get_voltage()
        status = format(self.get_status(), "03b")

        print(f"IP: {self.rudi_ip_address}, DeviceID: {self.module_address}")
        print(
            f"Hardware version: {card_version[0]}, Firmware version: {card_version[1]}"
        )
        print(f"Voltage: {voltage:.3f} [V]")
        print(f"Range: {self.range} [V]")
        print(f"Status: {status}")

        print("The DAC Card is:")
        [print(f" - {self.states_map[k]}") for k, v in enumerate(status) if v == "1"]
