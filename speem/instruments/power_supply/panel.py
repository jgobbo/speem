from .common import *
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .instrument import PowerSupplyController

from autodidaqt.panels import BasicInstrumentPanel
from autodidaqt.ui import (
    CollectUI,
    vertical,
    horizontal,
    submit,
    group,
    combo_box,
    button,
    label,
    numeric_input,
)

__all__ = ("PowerSupplyPanel",)


class PowerSupplyPanel(BasicInstrumentPanel):
    TITLE = "Power Supply"
    SIZE = (800, 400)
    DEFAULT_OPEN = True
    settings = PowerSupplySettings
    instrument: "PowerSupplyController"

    def assign_lens_table(self, ui_value):
        if ui_value:
            lens_table = self.instrument.lens_tables[
                self.ui["raw-table"].currentIndex()
            ]
            self.ui["metadata"].setText(lens_table.metadata)
            for key, val in lens_table.table.items():
                try:
                    self.ui[key.name].setText(val)
                except KeyError:
                    print(f"Element:{key} doesn't exist.")

    def apply(self, table: dict):
        # converting and scaling values before sending to instrument driver
        scaling = float(self.ui["desired-energy"].text()) / float(
            self.ui["designed-energy"].text()
        )
        table = {Electrode[key]: float(val) * scaling for key, val in table.items()}

        self.instrument.driver.apply_table(LensTable(table=table, name="from panel"))

    def stop(self, _):  # need to accept button value but don't use it
        stop_table = LensTable(table=dict(zip(Electrode, [0] * len(Electrode))))
        self.apply(stop_table)

    def layout(self):
        def electrode_layout(name: str, electrodes: list[Electrode]):
            def electrode_numeric(electrode: Electrode):
                input = numeric_input("0", id=electrode.name)
                if electrode not in self.settings.electrode_configuration.keys():
                    input.setStyleSheet("background-color:rgb(255,90,90);")

                return input

            return group(
                name,
                vertical(
                    *[
                        horizontal(label(electrode.name), electrode_numeric(electrode))
                        for electrode in electrodes
                    ]
                ),
            )

        with CollectUI(self.ui):
            vertical(
                group(
                    "lens voltages",
                    horizontal(
                        vertical(
                            group(
                                "raw table",
                                combo_box(
                                    [
                                        table.name
                                        for table in self.instrument.lens_tables
                                    ],
                                    id="raw-table",
                                ),
                            ),
                            group(
                                "metadata",
                                label(
                                    "assign a lens table to view it's metadata",
                                    id="metadata",
                                ),
                            ),
                        ),
                        vertical(
                            group(
                                "designed energy [eV]",
                                numeric_input("1", id="designed-energy"),
                            ),
                            group(
                                "desired energy [eV]",
                                numeric_input("1", id="desired-energy"),
                            ),
                        ),
                        button("Assign Lens Table", id="assign-table"),
                    ),
                ),
                horizontal(
                    electrode_layout(
                        "lens 0", [Electrode.V00, Electrode.V01, Electrode.V02],
                    ),
                    electrode_layout(
                        "lens 1", [Electrode.V11, Electrode.V12, Electrode.V13],
                    ),
                    electrode_layout(
                        "lens 2", [Electrode.V21, Electrode.V22, Electrode.V23],
                    ),
                    electrode_layout(
                        "deflector 0", [Electrode.D00, Electrode.D01, Electrode.D02],
                    ),
                    electrode_layout(
                        "stigmator",
                        [Electrode.ST0, Electrode.ST1, Electrode.ST2, Electrode.ST3,],
                    ),
                    electrode_layout(
                        "deflector 1", [Electrode.D10, Electrode.D11, Electrode.D12],
                    ),
                    electrode_layout(
                        "lens 3", [Electrode.V31, Electrode.V32, Electrode.V33],
                    ),
                    electrode_layout(
                        "detector",
                        [
                            Electrode.BASELINE,
                            Electrode.MESH,
                            Electrode.MCP,
                            Electrode.ANODE,
                        ],
                    ),
                ),
                button("APPLY", id="apply"),
                button("EMERGENCY STOP", id="e-stop"),
                widget=self,  # very important but idk why
            )

        self.ui["assign-table"].subject.subscribe(self.assign_lens_table)
        self.ui["e-stop"].subject.subscribe(self.stop)
        submit("apply", [electrode.name for electrode in Electrode], self.ui).subscribe(
            self.apply
        )
