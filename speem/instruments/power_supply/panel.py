import os
from pathlib import Path

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

ROOT = Path(__file__).parent


class PowerSupplyPanel(BasicInstrumentPanel):
    TITLE = "Power Supply"
    SIZE = (800, 400)
    DEFAULT_OPEN = True
    TABLE_FOLDER = ROOT / Path("lens_tables")
    ELECTRODE_LIST = [
        "V00",
        "V01",
        "V02",
        "V11",
        "V12",
        "V13",
        "V21",
        "V22",
        "V23",
        "V31",
        "V32",
        "V33",
        "S0",
        "S1",
        "S2",
        "S3",
        "D00",
        "D01",
        "D02",
        "D10",
        "D11",
        "D12",
        "Baseline",
        "Anode",
        "MCP",
    ]
    lens_tables: dict[str, dict] = {}

    def __init__(self, *args, **kwargs):
        self.import_all_table_files()
        super().__init__(*args, **kwargs)

    def import_all_table_files(self):
        for filename in os.listdir(self.TABLE_FOLDER):
            self.lens_tables[filename] = self.import_table_file(
                self.TABLE_FOLDER / Path(filename)
            )

    def import_table_file(self, fname):
        with open(fname, "r") as f:
            table = {"metadata": f.readline()}
            for line in f:
                element, voltage = [item.strip() for item in line.split(":")]
                if element in ("Anode", "MCP"):
                    print(
                        f"""Anode and MCP voltages should never be included in lens tables.
                            {fname} contains Anode and MCP values"""
                    )
                else:
                    table[element] = voltage
        print(table)
        return table

    def assign_lens_table(self, ui_value):
        if ui_value:
            table = self.lens_tables[self.ui["raw-table"].currentText()]
            self.ui["metadata"].setText(table["metadata"])
            for key, val in table.items():
                if key != "metadata":
                    try:
                        self.ui[key].setText(val)
                    except KeyError:
                        print(f"Element:{key} doesn't exist.")

    def apply(self, table: dict):
        # converting and scaling values before sending to instrument driver
        scaling = float(self.ui["desired-energy"].text()) / float(
            self.ui["designed-energy"].text()
        )
        table = {key: float(val) * scaling for key, val in table.items()}

        self.instrument.driver.bogus_set_voltages(table)

    def stop(self, _):  # need to accept button value but don't use it
        self.apply(dict(zip(self.ELECTRODE_LIST, [0] * len(self.ELECTRODE_LIST))))

    def layout(self):
        def element_layout(name: str, element_names: list[str]):
            return group(
                name,
                vertical(
                    *[
                        horizontal(label(element), numeric_input("0", id=element))
                        for element in element_names
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
                                combo_box(self.lens_tables.keys(), id="raw-table"),
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
                    element_layout("lens 0", ["V00", "V01", "V02"]),
                    element_layout("lens 1", ["V11", "V12", "V13"]),
                    element_layout("lens 2", ["V21", "V22", "V23"]),
                    element_layout("deflector 0", ["D00", "D01", "D02"]),
                    element_layout("stigmator", ["S0", "S1", "S2", "S3"]),
                    element_layout("deflector 1", ["D10", "D11", "D12"]),
                    element_layout("lens 3", ["V31", "V32", "V33"]),
                    element_layout("detector", ["Anode", "MCP", "Baseline"]),
                ),
                button("APPLY", id="apply"),
                button("EMERGENCY STOP", id="e-stop"),
                widget=self,  # very important but idk why
            )

        self.ui["assign-table"].subject.subscribe(self.assign_lens_table)
        self.ui["e-stop"].subject.subscribe(self.stop)
        submit("apply", self.ELECTRODE_LIST, self.ui).subscribe(self.apply)
