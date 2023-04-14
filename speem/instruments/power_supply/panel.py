import asyncio
from functools import partial
from .common import *
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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .instrument import PowerSupplyController
    from autodidaqt.widgets import NumericEdit

__all__ = ("PowerSupplyPanel",)


def safe_float(string: str) -> float:
    try:
        return float(string)
    except ValueError:
        return 0.0


"""
List of changes to check
1. Lens-table metadata automatically updates when table is selected in dropdown
2. lens-table assign is now apply
3. anode and mcp are now labels and can only be changed with buttons
4. all terminal numerics automatically apply voltage when changed and have validation
5. invalid terminals has id "None"
6. TCP master was consolidated as a potential fix
"""


class PowerSupplyPanel(BasicInstrumentPanel):
    TITLE = "Power Supply"
    SIZE = (800, 400)
    DEFAULT_OPEN = True
    settings = PowerSupplySettings
    instrument: "PowerSupplyController"

    DFX = {
        Corrector.D00: 1,
        Corrector.D02: -1,
        Corrector.D10: -1,
        Corrector.D12: 1,
    }  # maybe should be x2 on the second set
    DFY = {Corrector.D01: -1, Corrector.D11: 1}

    STA = {
        Corrector.ST0: 1,
    }
    STB = {Corrector.ST1: 1, Corrector.ST2: -1}

    # D0X = {Corrector.D00: 1, Corrector.D02: -1}
    # D0Y = {Corrector.D01: 1}
    # D1X = {Corrector.D10: 1, Corrector.D12: -1}
    # D1Y = {Corrector.D11: 1}

    D00 = {Corrector.D00: 1}
    D01 = {Corrector.D01: 1}
    D02 = {Corrector.D02: 1}
    D10 = {Corrector.D10: 1}
    D11 = {Corrector.D11: 1}
    D12 = {Corrector.D12: 1}

    def update_metadata(self, _table_name: str) -> None:
        """
        Combo boxes' subjects contain their current text as a string, but we actually want the index.
        We also want the reactivity of subscribing to the subject, so we just ignore the value and take the index from the combo box.
        """

        self.ui["metadata"].setText(
            self.instrument.lens_tables[self.ui["raw-table"].currentIndex()].metadata
        )

    def apply_lens_table(self, ui_value):
        if ui_value:
            lens_table = self.instrument.lens_tables[
                self.ui["raw-table"].currentIndex()
            ]
            # self.ui["metadata"].setText(lens_table.metadata)

            scaling = float(self.ui["desired-energy"].text()) / float(
                self.ui["designed-energy"].text()
            )
            scaled_table = {
                electrode: voltage * scaling
                for electrode, voltage in lens_table.table.items()
            }
            for key, val in scaled_table.items():
                try:
                    self.ui[key.name].setText(str(val))
                except KeyError:
                    print(f"Electrode:{key} doesn't exist.")

    # def apply_table(self, table: dict):
    #     table = {Electrode[key]: safe_float(val) for key, val in table.items()}
    #     self.instrument.driver.apply_table(LensTable(table=table, name="from panel"))

    # def apply_detector(self, values: dict):
    #     for detector, voltage in values.items():
    #         self.instrument.driver.apply_voltage(
    #             Detector[detector], safe_float(voltage)
    #         )

    # def apply_detector(self, detector:Detector, voltage:str):
    #     self.instrument.driver.apply_voltage(detector, safe_float(voltage))

    # def apply_corrector(self, corrector: str, voltage: str):
    #     voltage = safe_float(voltage)

    #     if isinstance(corrector, Corrector):
    #         configuration = {corrector: 1}
    #     else:
    #         configuration: dict[Corrector, int] = getattr(self, corrector)
    #     for corrector, multiplier in configuration.items():
    #         # print(f"{corrector}: {multiplier}")
    #         self.instrument.driver.apply_voltage(
    #             corrector, safe_float(voltage * multiplier)
    #         )

    def apply_element(self, element: str, voltage: str):
        configuration: dict[Terminal, float] = getattr(self, element)
        for terminal, multiplier in configuration.items():
            self.instrument.driver.apply_voltage(
                terminal, safe_float(voltage * multiplier)
            )

    def shutdown_electrodes(self, button_val: bool) -> None:
        if button_val:
            # table = {}
            for electrode in self.settings.terminal_configuration.keys():
                if isinstance(electrode, Electrode):
                    self.ui[electrode.name].setText("0")
            #         table[electrode.name] = 0
            # self.apply_table(table)

    def increment_voltage(
        self, button_val: bool, terminal: Terminal, increment: float
    ) -> None:
        if button_val:
            ui_element: "NumericEdit" = self.ui[terminal.name]
            output_voltage = safe_float(ui_element.text()) + increment
            self.instrument.driver.apply_voltage(terminal, output_voltage)
            ui_element.setText(str(output_voltage))

    async def _apply_anode(self, voltage: float) -> None:
        self.instrument.driver.apply_voltage(Detector.ANODE, voltage)
        self.ui[Detector.ANODE.name].setText(str(voltage))
        await asyncio.sleep(1)

    async def ramp_detector(self, button_val: bool) -> None:
        if button_val:
            starting_voltage = self.instrument.driver.modules[
                Detector.ANODE
            ].get_voltage()
            if starting_voltage < 1500:
                next_voltage = 1500
            else:
                next_voltage = starting_voltage
            while next_voltage < 2500:
                await self._apply_anode(next_voltage)
                next_voltage += 500
            while next_voltage < 4000:
                await self._apply_anode(next_voltage)
                next_voltage += 100
            await self._apply_anode(4000)

            self.instrument.driver.apply_voltage(Detector.MCP, 300)
            self.ui[Detector.MCP.name].setText(str(300))

    async def shutdown_detector(self, button_val: bool) -> None:
        if button_val:
            starting_voltage = self.instrument.driver.modules[
                Detector.ANODE
            ].get_voltage()
            next_voltage = starting_voltage - 100
            while next_voltage > 3000:
                await self._apply_anode(next_voltage)
                next_voltage -= 100
            while next_voltage > 1000:
                await self._apply_anode(next_voltage)
                next_voltage -= 500
            await self._apply_anode(0)

            for detector in [Detector.MCP, Detector.GRID]:
                self.instrument.driver.apply_voltage(detector, 0)
                self.ui[detector.name].setText(str(0))

    def layout(self):
        def terminal_numeric(terminal: Terminal):
            if terminal not in self.settings.terminal_configuration:
                input = numeric_input(
                    "n/a",
                    id=None,
                )
                input.setStyleSheet("background-color:rgb(255,90,90);")
            else:
                validation_settings = {
                    "bottom": self.instrument.driver.modules[terminal].range.min,
                    "top": self.instrument.driver.modules[terminal].range.max,
                    "decimals": 3,
                }
                input = numeric_input(
                    str(self.instrument.driver.modules[terminal].get_voltage()),
                    id=terminal.name,
                    validation_settings=validation_settings,
                )
                # quick application of voltage whenever text is changed
                input.subject.subscribe(
                    lambda voltage: self.instrument.driver.apply_voltage(
                        terminal, safe_float(voltage)
                    )
                )
            return input

        def terminal_label(terminal: Terminal):
            if terminal not in self.settings.terminal_configuration:
                ui_label = label("n/a", id=terminal.name)
                ui_label.setStyleSheet("background-color:rgb(255,90,90);")
            else:
                ui_label = label(
                    str(self.instrument.driver.modules[terminal].get_voltage()),
                    id=terminal.name,
                )
            return ui_label

        def terminal_layout(name: str, terminals: list[Terminal]):
            return group(
                name,
                vertical(
                    *[
                        horizontal(label(terminal.name), terminal_numeric(terminal))
                        for terminal in terminals
                    ]
                ),
            )

        def element_numeric(element: str):
            # TODO: add validation
            input = numeric_input("0", id=element)
            input.subject.subscribe(partial(self.apply_element, element))
            return input

        def element_layout(
            name: str, elements: list[str]
        ):  # elements are collections of terminals
            return group(
                name,
                vertical(
                    *[
                        horizontal(label(element), element_numeric(element))
                        for element in elements
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
                                    # "assign a lens table to view it's metadata",
                                    "select a lens table to view it's metadata",
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
                        # button("Assign Lens Table", id="assign-table"),
                        button("Apply Lens Table", id="apply-table"),
                    ),
                ),
                horizontal(
                    group(
                        "Imaging Lenses",
                        terminal_layout("baseline", [Electrode.BASELINE]),
                        terminal_layout(
                            "lens 0",
                            [Electrode.V00, Electrode.V01, Electrode.V02],
                        ),
                        terminal_layout(
                            "lens 1",
                            [Electrode.V11, Electrode.V12, Electrode.V13],
                        ),
                        terminal_layout(
                            "lens 2",
                            [Electrode.V21, Electrode.V22, Electrode.V23],
                        ),
                        terminal_layout(
                            "lens 3",
                            [Electrode.V31, Electrode.V32, Electrode.V33],
                        ),
                    ),
                    group(
                        "Correction Lenses",
                        element_layout("deflector", ["DFX", "DFY"]),
                        element_layout(
                            "stigmator",
                            ["STA", "STB"],
                        ),
                        # element_layout("deflector 0", ["D0X", "D0Y"],),
                        # element_layout("deflector 1", ["D1X", "D1Y"],),
                        terminal_layout(
                            "deflector 0",
                            [Corrector.D00, Corrector.D01, Corrector.D02],
                        ),
                        terminal_layout(
                            "deflector 1",
                            [Corrector.D10, Corrector.D11, Corrector.D12],
                        ),
                    ),
                    group(
                        "Detector",
                        vertical(
                            horizontal(
                                label("Anode"),
                                terminal_label(Detector.ANODE),
                                button("<", id="anode-minus"),
                                button(">", id="anode-plus"),
                            ),
                            horizontal(
                                label("MCP"),
                                terminal_label(Detector.MCP),
                                button("<", id="mcp-minus"),
                                button(">", id="mcp-plus"),
                            ),
                            horizontal(
                                label("Grid"),
                                terminal_numeric(Detector.GRID),
                            ),
                        ),
                    ),
                    # terminal_layout(
                    #     "detector",
                    #     [
                    #         Detector.GRID,
                    #         Detector.MCP,
                    #         Detector.ANODE,
                    #     ],
                    # ),
                ),
                horizontal(
                    # vertical(
                    #     button("Apply Table", id="apply-table"),
                    #     button("Shutdown Lenses", id="shutdown-lenses"),
                    # ),
                    button("Shutdown Electrodes", id="shutdown-electrodes"),
                    vertical(
                        # button("Apply Detector", id="apply-detector"),
                        button("Ramp Detector", id="ramp-detector"),
                        button("Shutdown Detector", id="shutdown-detector"),
                    ),
                ),
                widget=self,
            )

        self.ui["raw-table"].subject.subscribe(self.update_metadata)
        # self.ui["assign-table"].subject.subscribe(self.apply_lens_table)
        self.ui["apply-table"].subject.subscribe(self.apply_lens_table)
        self.ui["shutdown-electrodes"].subject.subscribe(self.shutdown_electrodes)
        self.ui["ramp-detector"].subject.subscribe(
            lambda button_val: asyncio.create_task(self.ramp_detector(button_val))
        )
        self.ui["shutdown-detector"].subject.subscribe(
            lambda button_val: asyncio.create_task(self.shutdown_detector(button_val))
        )

        self.ui["anode-plus"].subject.subscribe(
            partial(self.increment_voltage, terminal=Detector.ANODE, increment=10)
        )
        self.ui["anode-minus"].subject.subscribe(
            partial(self.increment_voltage, terminal=Detector.ANODE, increment=-10)
        )
        self.ui["mcp-plus"].subject.subscribe(
            partial(self.increment_voltage, terminal=Detector.MCP, increment=10)
        )
        self.ui["mcp-minus"].subject.subscribe(
            partial(self.increment_voltage, terminal=Detector.MCP, increment=-10)
        )

        # submit(
        #     "apply-table", [electrode.name for electrode in Electrode], self.ui
        # ).subscribe(self.apply_table)

        # for element in ["DFX", "DFY", "STA", "STB"]:
        #     self.ui[element].subject.subscribe(
        #         partial(self.apply_corrector, element)
        #     )

        # for corrector in Corrector:
        #     self.ui[corrector.name].subject.subscribe(
        #         partial(self.apply_corrector, corrector)
        #     )

        # submit(
        #     "apply-detector", [detector.name for detector in Detector], self.ui
        # ).subscribe(self.apply_detector)
