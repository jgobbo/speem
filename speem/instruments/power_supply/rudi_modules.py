from dataclasses import dataclass
from enum import IntEnum
import math
import modbus_tk.defines as cst
from modbus_tk.modbus_tcp import TcpMaster

__all__ = [
    "RudiHV",
    "RudiDAC",
]

IP_ADDRESS = "192.168.202.2"
BYTE = 1
WORD = 2


def dataToNumber(data):
    dataL = data[0] << 16
    dataLR = dataL | data[1]
    if (dataLR >> 31) == 1:
        dataLR = dataLR - (2 ** 32)
    return dataLR


def dataToSignedNumber(data):
    dataL = data[0] << 15
    dataLR = dataL | data[1]
    unsigned = dataLR % 2 ** 16
    signed = unsigned - 2 ** 16 if unsigned >= 2 ** 15 else unsigned
    return signed * (10 ** (-3))


def softwareConvert(software) -> tuple[str, str]:
    """
    Gets the decimal number and convert it to a binary system. Separates the last 5 chars and converts its again
    to decimal - it's the firmware version. The other chars convert to decimal and add between each char
    a dot - it's hardware version.

    :param software: (int) Decimal software number to convert.
    :return: List of [hardware, firmware] in string format.
    """
    b_hardware = bin(software)[2:-5]
    dec_hardware = str(int(b_hardware, 2))
    hardware = f"{dec_hardware[1]}.{dec_hardware[1]}.{dec_hardware[2:]}"

    b_firmware = bin(software)[-5:]
    firmware = str(int(b_firmware, 2))

    return hardware, firmware


def calibrationPointCheck(points) -> bool:
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
            2: "Transparent",
            3: "Positive High",
            4: "Negative High",
            5: "Positive Low",
            6: "Negative Low",
            7: "Short Output",
        }[self.value]


@dataclass
class HVOffsets:
    """
    Map of addresses of HV card registers 
    that are queried using the ModbusTCP protocol.
    """

    STARTING_ADDRESS = 0
    VOLTAGE_SETPOINT_offset = 2
    OPERATE_offset = 4
    WORKING_MODE_offset = 5
    STATUS_offset = 6
    VOLTAGE_offset = 7
    CARD_VERSION_offset = 9
    CAL_POINT_NUMBER_offset = 10
    SECURITY_WORD_offset = 11
    VOLTAGE_RANGE_offset = 12
    BIT_MINIMUM_offset = 14
    DA_offset = 16
    UA_offset = 18
    DB_offset = 20
    UB_offset = 22


@dataclass
class RudiHV:
    module_address: int
    rudi_ip_address: str = IP_ADDRESS
    offsets = HVOffsets
    states_map = {
        0: "After the reset",
        1: "Dual-band card",
        2: "Operate",
        3: "Output fail",
        4: "Output short",
        5: "Low Calib Fail",
        6: "High Calib Fail",
        7: "Ready to set up",
    }  # Available card states, which are encoded in the register in the form of an 8-bit map.
    master: TcpMaster = None
    is_dual_channel: bool = None
    high_range: FloatRange = None
    low_range: FloatRange = None
    min_output: float = None
    mode: HVMode = None

    def __post_init__(self):
        self.master = TcpMaster(self.rudi_ip_address, timeout_in_sec=0.1)

        status = self.get_status()
        self.mode = self.get_mode()

        self.is_dual_channel = status & 0b01000000 != 0

        self.set_mode(HVMode.POSITIVE_HIGH)
        self.high_range = FloatRange(self.get_min(), self.get_max())
        self.min_output = self.high_range.min
        if self.is_dual_channel:
            self.set_mode(HVMode.POSITIVE_LOW)
            self.low_range = FloatRange(self.get_min(), self.get_max())
            self.min_output = self.low_range.min

        self.set_mode(self.mode)

    def get_voltage(self) -> float:
        data = self.master.execute(
            self.module_address,
            cst.READ_HOLDING_REGISTERS,
            self.offsets.VOLTAGE_offset,
            WORD,
        )
        value = dataToNumber(data)
        voltage = truncate(value * (10 ** (-3)), 3)
        return (
            voltage
            if self.mode in {HVMode.POSITIVE_HIGH, HVMode.POSITIVE_LOW}
            else -voltage
        )

    def get_setpoint(self) -> float:
        data = self.master.execute(
            self.module_address,
            cst.READ_HOLDING_REGISTERS,
            self.offsets.VOLTAGE_SETPOINT_offset,
            WORD,
        )
        value = dataToNumber(data)
        voltage = truncate(value * (10 ** (-3)), 3)
        return voltage

    def set_setpoint(self, voltage: float) -> None:
        if voltage == 0:
            return self.set_mode(HVMode.SHORT_OUTPUT)

        is_positive = voltage > 0
        voltage = abs(voltage)

        if self.is_dual_channel and voltage in self.low_range:
            self.set_mode(HVMode.POSITIVE_LOW if is_positive else HVMode.NEGATIVE_LOW)
            return self._set_setpoint(voltage)

        if voltage in self.high_range:
            self.set_mode(HVMode.POSITIVE_HIGH if is_positive else HVMode.NEGATIVE_HIGH)
            return self._set_setpoint(voltage)

        raise OutOfRangeError(
            f"Desired output voltage: {voltage} is outside of module {self.module_address}'s ranges: {self.low_range}, {self.high_range}."
        )

    def _set_setpoint(self, voltage: float) -> None:
        data = hex(int(voltage * 16 * (10 ** 3)) & (2 ** 32 - 1))[2:].zfill(9)
        self.master.execute(
            self.module_address,
            cst.WRITE_MULTIPLE_REGISTERS,
            self.offsets.VOLTAGE_SETPOINT_offset,
            output_value=[int(data[0:4], 16), int(data[4:8], 16)],
        )

    def set_mode(self, mode: HVMode) -> None:
        if mode is not self.mode:
            self.mode = mode
            self.master.execute(
                self.module_address,
                cst.WRITE_SINGLE_REGISTER,
                self.offsets.WORKING_MODE_offset,
                output_value=self.mode,
            )

    def get_mode(self) -> HVMode:
        return HVMode(
            self.master.execute(
                self.module_address,
                cst.READ_HOLDING_REGISTERS,
                self.offsets.WORKING_MODE_offset,
                WORD,
            )[0]
        )

    def get_max(self) -> float:
        data = self.master.execute(
            self.module_address,
            cst.READ_HOLDING_REGISTERS,
            self.offsets.VOLTAGE_RANGE_offset,
            WORD,
        )
        return truncate(dataToNumber(data) * (10 ** (-3)), 3)

    def get_min(self) -> float:
        data = self.master.execute(
            self.module_address,
            cst.READ_HOLDING_REGISTERS,
            self.offsets.UA_offset,
            WORD,
        )
        return truncate(dataToNumber(data) * (10 ** (-3)), 3)

    def get_status(self):
        return self.master.execute(
            self.module_address,
            cst.READ_HOLDING_REGISTERS,
            self.offsets.STATUS_offset,
            BYTE,
        )[0]

    def test(self, mode):
        return self.master.execute(
            self.module_address,
            cst.WRITE_SINGLE_REGISTER,
            self.offsets.STATUS_offset,
            output_value=mode,
        )

    def get_version(self):
        data = self.master.execute(
            self.module_address,
            cst.READ_HOLDING_REGISTERS,
            self.offsets.CARD_VERSION_offset,
            WORD,
        )
        return softwareConvert(data[0])

    # def get_cal_point(self):
    #     data = self.master.execute(
    #         self.module_address,
    #         cst.READ_HOLDING_REGISTERS,
    #         self.offsets.CAL_POINT_NUMBER_offset,
    #         WORD,
    #     )
    #     return data

    def show_info(self):
        card_version = self.get_version()
        voltage = self.get_voltage()
        setpoint = self.get_setpoint()
        range = self.get_max()
        min = self.get_min()
        mode = self.get_mode()
        status = format(self.get_status(), "08b")

        print(f"IP: {self.rudi_ip_address}, DeviceID: {self.module_address}")
        print(
            f"Hardware version: {card_version[0]}, Firmware version: {card_version[1]}"
        )
        print(f"Voltage: {voltage} [V], Setpoint: {setpoint} [V]")
        print(f"Mode: {mode}")
        print(f"Range: {range} [V]")
        print(f"Minimum Voltage: {min} [V]")
        print(f"Status: {status}")

        print("The HV Card is:")
        [print(f" - {self.states_map[k]}") for k, v in enumerate(status) if v == "1"]


@dataclass
class DACOffsets:
    """
    Map of addresses of DAC card registers 
    that are queried using the ModbusTCP protocol.
    """

    STARTING_ADDRESS = 0
    VOLTAGE_offset = 2
    STATUS_offset = 4
    SOFTWARE_VERSION_offset = 5
    CAL_POINT_NUMBER_offset = 6
    SECURITY_WORD_offset = 7
    DA_offset = 8
    UA_offset = 10
    DB_offset = 12
    UB_offset = 14


@dataclass
class RudiDAC:
    module_address: int
    rudi_ip_address: str = IP_ADDRESS
    offsets = DACOffsets
    states_map = {
        0: "After the reset",
        1: "Dual-band card",
        2: "Operate",
        3: "Output fail",
        4: "Output short",
        5: "Low Calib Fail",
        6: "High Calib Fail",
        7: "Ready to set up",
    }  # states were only specified for the HV cards, would need to talk to PREVAC to verify these
    master: TcpMaster = None
    is_dual_channel: bool = None
    range = FloatRange(-50, 50)
    min_output = 0.0

    def __post_init__(self):
        self.master = TcpMaster(self.rudi_ip_address, timeout_in_sec=0.1)

    def get_voltage(self) -> float:
        data = self.master.execute(
            self.module_address,
            cst.READ_HOLDING_REGISTERS,
            self.offsets.VOLTAGE_offset,
            WORD,
        )
        value = dataToNumber(data)
        voltage = truncate(value * (10 ** -6), 3)
        return voltage

    # def get_setpoint(self) -> float:
    #     data = self.master.execute(
    #         self.module_address,
    #         cst.READ_HOLDING_REGISTERS,
    #         self.offsets.VOLTAGE_SETPOINT_offset,
    #         WORD,
    #     )
    #     value = dataToNumber(data)
    #     voltage = truncate(value * (10 ** (-3)), 3)
    #     return voltage

    def set_setpoint(self, voltage: float) -> None:
        if voltage in self.range:
            return self._set_setpoint(voltage)

        raise OutOfRangeError(
            f"Desired output voltage: {voltage} is outside of module {self.module_address}'s range: {self.range}."
        )

    def _set_setpoint(self, voltage: float) -> None:
        data = hex(int(voltage * 16 * (10 ** 6)) & (2 ** 32 - 1))[2:].zfill(9)
        self.master.execute(
            self.module_address,
            cst.WRITE_MULTIPLE_REGISTERS,
            self.offsets.VOLTAGE_offset,
            output_value=[int(data[0:4], 16), int(data[4:8], 16)],
        )

    # def set_mode(self, mode: HVMode) -> None:
    #     return self.master.execute(
    #         self.module_address,
    #         cst.WRITE_SINGLE_REGISTER,
    #         self.offsets.STATUS_offset,
    #         output_value=mode,
    #     )

    # def get_mode(self) -> HVMode:
    #     return HVMode(
    #         self.master.execute(
    #             self.module_address,
    #             cst.READ_HOLDING_REGISTERS,
    #             self.offsets.WORKING_MODE_offset,
    #             WORD,
    #         )[0]
    #     )

    # def get_range(self) -> float:
    #     data = self.master.execute(
    #         self.module_address,
    #         cst.READ_HOLDING_REGISTERS,
    #         self.offsets.VOLTAGE_RANGE_offset,
    #         WORD,
    #     )
    #     return self.truncate(self.dataToNumber(data) * (10 ** (-3)), 3)

    # def get_min(self) -> float:
    #     data = self.master.execute(
    #         self.module_address,
    #         cst.READ_HOLDING_REGISTERS,
    #         self.offsets.UA_offset,
    #         WORD,
    #     )
    #     return truncate(dataToNumber(data) * (10 ** (-3)), 3)

    def get_status(self):
        return self.master.execute(
            self.module_address,
            cst.READ_HOLDING_REGISTERS,
            self.offsets.STATUS_offset,
            BYTE,
        )[0]

    def get_version(self):
        data = self.master.execute(
            self.module_address,
            cst.READ_HOLDING_REGISTERS,
            self.offsets.SOFTWARE_VERSION_offset,
            WORD,
        )
        return softwareConvert(data[0])

    def show_info(self):
        card_version = self.get_version()
        voltage = self.get_voltage()
        status = format(self.get_status(), "08b")

        print(f"IP: {self.rudi_ip_address}, DeviceID: {self.module_address}")
        print(
            f"Hardware version: {card_version[0]}, Firmware version: {card_version[1]}"
        )
        print(f"Voltage: {voltage} [V]")
        print(f"Range: {self.range} [V]")
        print(f"Status: {status}")

        print("The DAC Card is:")
        [print(f" - {self.states_map[k]}") for k, v in enumerate(status) if v == "1"]
