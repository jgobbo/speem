from pathlib import Path
from setuptools import setup, find_packages

ROOT = Path(__file__).parent

VERSION = "0.0.1"
PACKAGE_NAME = "speem"
AUTHOR = "Jacob Gobbo, Conrad Stansbury"
AUTHOR_EMAIL = "jgobbo@berkeley.edu"
URL = ""

LICENSE = "MIT License"
DESCRIPTION = "speem daq package"
LONG_DESCRIPTION = (ROOT / "README.md").read_text()
LONG_DESC_TYPE = "text/markdown"

with open(ROOT / "requirements.txt") as f:
    INSTALL_REQUIRES = f.read().splitlines()

setup(
    name=PACKAGE_NAME,
    version=VERSION,
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    long_description_content_type=LONG_DESC_TYPE,
    author=AUTHOR,
    license=LICENSE,
    author_email=AUTHOR_EMAIL,
    url=URL,
    install_requires=INSTALL_REQUIRES,
    packages=find_packages(),
)
