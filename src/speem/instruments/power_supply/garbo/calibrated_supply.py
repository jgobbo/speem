import warnings
from dataclasses import dataclass, InitVar
import contextlib
from pathlib import Path
from typing import Any, Union, Dict
import toml
import pandas as pd

from .hvc20_low_level import setup, initialize, finalize, set_dac20, set_hv, burst

ROOT_PATH = Path(__file__).parent

@dataclass
class VoltageConfig:
    name: str
    description: str
    ramp: float # Volts/second

    address: InitVar[str]
    hw_address: int = None
    is_hv: bool = False

    @property
    def should_ramp(self):
        return self.ramp > 0

    def __post_init__(self, address: str):
        if address.startswith('D'):
            self.is_hv = False
            self.hw_address = int(address[1:])
        else:
            self.is_hv = True
            self.hw_address = int(address)


def clamp(v, low, high):
    if v <= low:
        return low
    if v >= high:
        return high
    return v


@dataclass
class CalibratedSupplyConfig:
    name: str
    author: str
    date: str

    lv_calibration: float

    definitions_file: InitVar[str]
    hv_calibration_file: InitVar[str]
    lens_table_file: InitVar[str]

    notes: str = ''
    definitions: Dict[str, VoltageConfig] = None
    lens_tables: Dict[str, Dict[str, float]] = None
    hv_calibration: Any = None

    def __post_init__(self, definitions_file: str, hv_calibration_file: str, lens_table_file: str):
        def resolve(p: str):
            if Path(p).exists():
                return Path(p)

            return ROOT_PATH / p

        with open(str(resolve(definitions_file))) as f:
            defs = [VoltageConfig(**definition) for definition in pd.read_csv(f, sep=r',\s*', engine='python').to_dict(orient='records')]
            self.definitions = {d.name: d for d in defs}

        with open(str(resolve(hv_calibration_file))) as f:
            calibrations = pd.read_csv(f, sep=r',\s*', engine='python').to_dict(orient='records')
            calibrations = [c for c in calibrations if set(c['name']) != {'-',}]
            self.hv_calibration = {c['name']: c for c in calibrations}

        with open(str(resolve(lens_table_file))) as f:
            raw_tables = pd.read_csv(f, sep=r',\s*', engine='python').to_dict(orient='records')
            tables = {}
            for table in raw_tables:
                name = table.pop('name')
                tables[name] = table
                if set(table.keys()) != set(self.definitions.keys()):
                    raise ValueError('Lens Table and Definitions refer to different lenses!')

            # always add a zero table
            tables['ZERO_EVERYTHING'] = {k: 0. for k in self.definitions.keys()}

            self.lens_tables = tables


class CalibratedSupply:
    """
    An abstraction around the Scienta 7048 power supply that handles dealing with calibrations, addresses,
    and provides a property based interface to the power supply
    """
    config: CalibratedSupplyConfig
    _lens_table: str = None
    _burst_lock = False
    _voltage_cache: Dict[str, float]

    @contextlib.contextmanager
    def burst(self):
        self._burst_lock = True
        yield
        self._burst_lock = False
        print('Burst')
        burst()

    @classmethod
    def from_config(cls, path: Union[str, Path]):
        with open(str(path)) as f:
            config = toml.load(f)

        return cls(config=CalibratedSupplyConfig(**config))

    def __init__(self, config: CalibratedSupplyConfig):
        self.__dict__['config'] = config
        self._voltage_cache = {}

    def startup(self):
        initialize()
        setup()

    def shutdown(self):
        finalize()

    @property
    def lens_table(self):
        return self._lens_table

    @lens_table.setter
    def lens_table(self, table_name):
        if table_name not in self.config.lens_tables:
            raise ValueError(f'Could     not find lens table {table_name} '
                             f'among {list(self.config.lens_tables.keys())}.')
        self._lens_table = table_name
        with self.burst():
            for k, v in self.config.lens_tables[table_name].items():
                setattr(self, k, v)

    @property
    def is_operational(self):
        return not any(v is None for v in self.voltages.values())

    @property
    def voltages(self):
        return {k: self._voltage_cache.get(k) for k in self.config.definitions.keys()}

    def _apply_voltage(self, name: str, nominal_voltage: float):
        definition = self.config.definitions[name]

        if definition.is_hv:
            calibration = self.config.hv_calibration[name]
            translated_voltage = int(((nominal_voltage - calibration['offset']) / calibration['maximum']) * (2 ** 16 - 1))
            calibrated_voltage = clamp(translated_voltage, 0, 2 ** 16 - 1)
            if translated_voltage != calibrated_voltage:
                warnings.warn(f'Voltage out of range: {nominal_voltage} trans:({translated_voltage}) on {definition}')
        else:
            calibrated_voltage = int(nominal_voltage / self.config.lv_calibration)

        print(f'Applying {nominal_voltage} cal:({calibrated_voltage}) to {definition}.')

        if definition.is_hv:
            set_hv(address=definition.hw_address, voltage=calibrated_voltage, period=2 ** 16 - 1)
        else:
            set_dac20(address=definition.hw_address, voltage=calibrated_voltage)

    def __getattr__(self, item):
        if item in self.config.definitions:
            return self._voltage_cache.get(item, None)

    def __setattr__(self, key, value):
        if key in self.config.definitions.keys():
            if self._burst_lock:
                self._apply_voltage(key, value)
            else:
                with self.burst():
                    self._apply_voltage(key, value)
        else:
            super().__setattr__(key, value)

