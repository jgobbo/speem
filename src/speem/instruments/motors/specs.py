from dataclasses import dataclass
from enum import Enum, StrEnum

from .drivers import HomeDirection


class RealAxis(StrEnum):
    X = "X"
    Y = "Y"
    Z = "Z"
    Theta = "Theta"
    Beta = "Beta"
    Phi = "Phi"
    x = "x"
    y = "y"


X_CENTER_MM = 20.5
Y_CENTER_MM = -12.6
x_CENTER_MM = 6.5
y_CENTER_MM = 3.9

Z_SAMPLE_STAGE_MM = -12.6

Y_CENTER_TO_SPEEM_FOCUS_MM = -36.61
Y_SPEEM_POSITION_BUFFER_MM = 5
y_CENTER_TO_SAMPLE_SURFACE_MM = 18.5

# global movement will be done in order of dictionary
SAMPLE_LOAD_POSITION = {
    RealAxis.Y: Y_CENTER_MM,
    RealAxis.X: X_CENTER_MM,
    RealAxis.y: y_CENTER_MM,
    RealAxis.x: x_CENTER_MM,
    RealAxis.Theta: 0.0,
    RealAxis.Z: Z_SAMPLE_STAGE_MM,
    RealAxis.Phi: 0.0,
    RealAxis.Beta: 0.0,
}
BAKEOUT_POSITION = {
    RealAxis.X: X_CENTER_MM,
    RealAxis.Y: Y_CENTER_MM,
    RealAxis.x: x_CENTER_MM,
    RealAxis.y: y_CENTER_MM,
    RealAxis.Theta: 0,
    RealAxis.Phi: 0,
    RealAxis.Beta: 0,
    RealAxis.Z: -300,  # mm
}
SPEEM_POSITION = {
    RealAxis.Z: Z_SAMPLE_STAGE_MM,
    RealAxis.x: x_CENTER_MM,
    RealAxis.X: X_CENTER_MM,
    RealAxis.Phi: 0.0,
    RealAxis.Beta: 0.0,
    RealAxis.Theta: 198,
    RealAxis.y: y_CENTER_MM + y_CENTER_TO_SAMPLE_SURFACE_MM,
    RealAxis.Y: Y_CENTER_MM + Y_CENTER_TO_SPEEM_FOCUS_MM + Y_SPEEM_POSITION_BUFFER_MM,
}
SPEEM_PINHOLE_POSITION = {
    RealAxis.Z: Z_SAMPLE_STAGE_MM - 25,
    RealAxis.x: x_CENTER_MM,
    RealAxis.y: y_CENTER_MM,
    RealAxis.Phi: 0.0,
    RealAxis.Beta: 0.0,
    RealAxis.Theta: 150,
    RealAxis.X: X_CENTER_MM - 12.257,
    RealAxis.Y: Y_CENTER_MM - 10,
}

XY_MM_TO_MICROSTEPS = 806_299.213

REAL_AXIS_SPECS = {
    RealAxis.X: {
        "unit": "mm",
        "unit_ratio": XY_MM_TO_MICROSTEPS,
        "home_direction": HomeDirection.NEGATIVE,
        "speed": 0.5,
        "default_soft_limits": (0, 30),
    },
    RealAxis.Y: {
        "unit": "mm",
        "unit_ratio": XY_MM_TO_MICROSTEPS,
        "home_direction": HomeDirection.POSITIVE,
        "speed": 0.5,
        "default_soft_limits": (-50, 0),
    },
    RealAxis.Z: {
        "unit": "mm",
        "unit_ratio": 2150,
        "home_direction": HomeDirection.POSITIVE,
        "speed": 0.5,
        "default_soft_limits": (-500, 0.1),
    },
    RealAxis.Theta: {
        "unit": "deg",
        "unit_ratio": 100,
        "home_direction": HomeDirection.NEGATIVE,
        "speed": 3.6,
        "default_soft_limits": (-0.5, 220),
    },
    RealAxis.Beta: {
        "unit": "deg",
        "unit_ratio": 288,
        "home_direction": HomeDirection.MANUAL,
        "speed": 0.1,
        "default_soft_limits": (-2, 2),
    },
    RealAxis.Phi: {
        "unit": "deg",
        "unit_ratio": 79,
        "home_direction": HomeDirection.MANUAL,
        "speed": 1,
        "default_soft_limits": (-90, 90),
    },
    RealAxis.x: {
        "unit": "mm",
        "unit_ratio": 2000,
        "home_direction": HomeDirection.NEGATIVE,
        "speed": 0.5,
        "default_soft_limits": (-0.1, 8),
    },
    RealAxis.y: {
        "unit": "mm",
        "unit_ratio": 2000,
        "home_direction": HomeDirection.NEGATIVE,
        "speed": 0.5,
        "default_soft_limits": (
            -0.1,
            y_CENTER_MM + y_CENTER_TO_SAMPLE_SURFACE_MM + 0.1,
        ),
    },
}


@dataclass
class VirtualAxisSpec:
    """
    Dataclass containing specs for a `VirtualAxisDriver`

    A real axis can be copied by supplying it as the only argument.
    """

    axes: list[RealAxis] | RealAxis
    scalings: list[float] = None
    offsets: list[float] = None
    soft_limits: tuple[float, float] = None
    unit: str = None
    speed: float = None

    def __post_init__(self):
        if isinstance(self.axes, RealAxis):
            for attr in ("scalings", "offsets", "soft_limits", "unit", "speed"):
                assert (
                    getattr(self, attr) is None
                ), "To copy a real axis, supply it as the only argument with the rest "
                "default as None."
        else:
            n_axes = len(self.axes)
            assert all(
                len(attribute) == n_axes for attribute in [self.scalings, self.offsets]
            )


class SampleLoadAxis(Enum):
    x = VirtualAxisSpec(
        axes=[RealAxis.x],
        scalings=[-1],
        offsets=[SAMPLE_LOAD_POSITION[RealAxis.x]],
        soft_limits=(-2, 2),
        unit="mm",
        speed=0.5,
    )
    y = VirtualAxisSpec(
        axes=[RealAxis.Z],
        scalings=[-1],
        offsets=[SAMPLE_LOAD_POSITION[RealAxis.Z]],
        soft_limits=(-2, 1000),
        unit="mm",
        speed=0.5,
    )


class SpeemAxis(Enum):
    x = VirtualAxisSpec(
        axes=[RealAxis.x],
        scalings=[1e-3],
        offsets=[SPEEM_POSITION[RealAxis.x]],
        soft_limits=(-3000, 3000),
        unit="um",
        speed=100,
    )
    y = VirtualAxisSpec(
        axes=[RealAxis.Z],
        scalings=[-1e-3],
        offsets=[SPEEM_POSITION[RealAxis.Z]],
        soft_limits=(-3000, 20_000),
        unit="um",
        speed=100,
    )
    z = VirtualAxisSpec(
        axes=[RealAxis.y],
        scalings=[-1e-3],
        offsets=[SPEEM_POSITION[RealAxis.y]],
        soft_limits=(-10_000, 1000),
        unit="um",
        speed=100,
    )
    theta = VirtualAxisSpec(
        axes=[RealAxis.Theta],
        scalings=[1],
        offsets=[SPEEM_POSITION[RealAxis.Theta]],
        soft_limits=(-15, 15),
        unit="deg",
        speed=0.5,
    )
    beta = VirtualAxisSpec(
        axes=[RealAxis.Beta],
        scalings=[1],
        offsets=[SPEEM_POSITION[RealAxis.Beta]],
        soft_limits=(-2, 2),
        unit="deg",
        speed=0.1,
    )
    phi = VirtualAxisSpec(
        axes=[RealAxis.Phi],
        scalings=[1],
        offsets=[SPEEM_POSITION[RealAxis.Phi]],
        soft_limits=(-45, 45),
        unit="deg",
        speed=1,
    )
    x_theta = VirtualAxisSpec(
        axes=[RealAxis.X],
        scalings=[1e-3],
        offsets=[SPEEM_POSITION[RealAxis.X]],
        soft_limits=(-5000, 5000),
        unit="um",
        speed=100,
    )
    z_theta = VirtualAxisSpec(
        axes=[RealAxis.Y],
        scalings=[-1e-3],
        offsets=[SPEEM_POSITION[RealAxis.Y] - Y_SPEEM_POSITION_BUFFER_MM],
        soft_limits=(-10_000, 2_000),
        unit="um",
        speed=100,
    )


class SpeemPinholeAxis(Enum):
    x_analyzer = VirtualAxisSpec(
        axes=[RealAxis.X],
        scalings=[1],
        offsets=[SPEEM_PINHOLE_POSITION[RealAxis.X]],
        soft_limits=(-10, 3),
        unit="mm",
        speed=0.5,
    )
    y_analyzer = VirtualAxisSpec(
        axes=[RealAxis.Z],
        scalings=[-1],
        offsets=[SPEEM_PINHOLE_POSITION[RealAxis.Z]],
        soft_limits=(-3, 3),
        unit="mm",
        speed=0.5,
    )
    z_analyzer = VirtualAxisSpec(
        axes=[RealAxis.Y],
        scalings=[-1],
        offsets=[SPEEM_PINHOLE_POSITION[RealAxis.Y]],
        soft_limits=(-1, 14.5),
        unit="mm",
        speed=0.5,
    )


class BakeoutAxis(Enum):
    X = VirtualAxisSpec(axes=RealAxis.X)
    Y = VirtualAxisSpec(axes=RealAxis.Y)
    Z = VirtualAxisSpec(axes=RealAxis.Z)
    x = VirtualAxisSpec(axes=RealAxis.x)
    y = VirtualAxisSpec(axes=RealAxis.y)
    Theta = VirtualAxisSpec(axes=RealAxis.Theta)


@dataclass
class GlobalPositionSpec:
    """
    Global position of all real axes. The position must specify the initial position of
    all real axes and the virtual axes that are active at the position.

    args:
        name: Name of the position. This is used to identify the position in the UI.
        axis_positions: Dictionary of real axis positions.
        virtual_axes: List of virtual axes active at the position.
    """

    name: str
    real_axis_positions: dict[RealAxis, float]
    virtual_axes: dict[str, VirtualAxisSpec]


class GlobalPosition(Enum):
    SAMPLE_LOAD = GlobalPositionSpec(
        name="Sample Load",
        real_axis_positions=SAMPLE_LOAD_POSITION,
        virtual_axes={axis.name: axis.value for axis in SampleLoadAxis},
    )
    BAKEOUT = GlobalPositionSpec(
        name="Bakeout",
        real_axis_positions=BAKEOUT_POSITION,
        virtual_axes={axis.name: axis.value for axis in BakeoutAxis},
    )
    SPEEM = GlobalPositionSpec(
        name="SPEEM",
        real_axis_positions=SPEEM_POSITION,
        virtual_axes={axis.name: axis.value for axis in SpeemAxis},
    )
    # SPEEM_PINHOLE = GlobalPositionSpec(
    #     name="SPEEM Pinhole",
    #     real_axis_positions=SPEEM_PINHOLE_POSITION,
    #     virtual_axes={axis.name: axis.value for axis in SpeemPinholeAxis},
    # )
