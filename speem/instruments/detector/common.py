from dataclasses import dataclass

__all__ = ("DetectorSettings",)


@dataclass
class DetectorSettings:
    acquisition_type: str = "seconds"
    integration_time: int = 100
    n_iterations: int = 5
    output_file_name: str = ""

    input_size: int = 4096
    data_reduction: int = 8
    data_size: int = input_size // data_reduction

    def as_message(self) -> str:
        return [
            f"{self.acquisition_type} ; type of acquisition (seconds or counts)",
            f"{self.integration_time} ; number of seconds or counts per integration",
            f"{self.n_iterations} ; number of iterations",
            f"{self.output_file_name} ; output file name",
        ]
