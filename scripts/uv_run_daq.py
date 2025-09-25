# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "autodidaqt",
#     "speem",
# ]
# ///

from autodidaqt import AutodiDAQt
from autodidaqt.mock import MockMotionController

app = AutodiDAQt(
    __name__,
    managed_instruments={
        "phony": MockMotionController,
    },
)


def main() -> None:
    app.start()


if __name__ == "__main__":
    main()
