from speem.instruments.power_supply.instrument import RudiEA2Driver
from speem.instruments.power_supply.common import (
    Corrector,
    Detector,
    Electrode,
)
from colorama import Fore, Style

driver = RudiEA2Driver()
test_tables: list[dict] = []
test_tables.append(
    {
        Electrode.BASELINE: 0.1,
        Detector.MCP: 0.1,
        Electrode.V13: 0.1,
        Electrode.V31: 0.1,
        Electrode.V32: 0.1,
        Corrector.ST0: 0.1,
        Corrector.ST1: 0.1,
        Corrector.ST2: 0.1,
    }
)

test_tables.append(
    {
        Electrode.BASELINE: 0,
        Detector.MCP: 0.1,
        Electrode.V13: 0.5,
        Electrode.V31: 0.2,
        Electrode.V32: 0.3,
        Corrector.ST0: -0.1,
        Corrector.ST1: -0.2,
        Corrector.ST2: -0.3,
    }
)

test_tables.append(
    {
        Electrode.BASELINE: 5,
        Detector.MCP: 0.01,
        Electrode.V13: -0.1,
        Electrode.V31: -0.1,
        Electrode.V32: -0.3,
        Corrector.ST0: -0.25,
        Corrector.ST1: 0.2,
        Corrector.ST2: 0.15,
    }
)

for test_table in test_tables:
    original = {
        electrode: voltage + test_table[Electrode.BASELINE]
        for electrode, voltage in test_table.items()
        if electrode is not Electrode.BASELINE
    }
    corrected = driver.correct_table(test_table)
    restored = {}
    for electrode, voltage in corrected.items():
        if electrode is not Electrode.BASELINE:
            restored[electrode] = voltage - corrected[Electrode.BASELINE]

    print(f"{Fore.GREEN}original - {original}")
    print(f"{Fore.BLUE}corrected - {corrected}")
    print(f"{Fore.GREEN}restored - {restored}{Style.RESET_ALL}")
