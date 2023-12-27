"""Manage recuair devices.

Usage: recuair-cli [options] <device>...
       recuair-cli -h | --help
       recuair-cli --version

Options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --debug               print debug logs
"""
import logging
import sys
from typing import List, NamedTuple, Optional

import requests
from bs4 import BeautifulSoup
from docopt import docopt

from recuair_cli import __version__

_LOGGER = logging.getLogger(__name__)


class StatusError(Exception):
    """Status of device can't be fetched."""


class Status(NamedTuple):
    """Represents device status."""

    device: str
    name: str
    temperature_in: int
    humidity_in: int
    temperature_out: int
    mode: str
    co2_ppm: int


def _strip_unit(value: str) -> str:
    """Strip unit from quantity and return only a quantity value."""
    return value.strip().partition(' ')[0]


def get_status(device: str) -> Status:
    """Return device status."""
    try:
        response = requests.get(f'http://{device}/', timeout=2)
        # XXX: Recuair doesn't return encoding properly.
        response.encoding = 'utf-8'
        response.raise_for_status()
    except requests.RequestException as error:
        _LOGGER.debug("Error encountered: %s", error)
        raise StatusError(f"Error fetching status of device {device}: {error}") from error
    _LOGGER.debug("Response: %s", response.text)

    try:
        content = BeautifulSoup(response.text, features="html.parser")
        container = content.find(class_='container')
        temperature_raw = container.find_all(class_='col-12')[1].find(class_='bigText').text
        in_data, _, temp_out = temperature_raw.strip().partition('%')
        temp_in, _, humi_in = in_data.strip().partition('/')
        mode_raw = container.find_all(class_='col-12')[3].find('span').text
        co2_raw = container.find_all(class_='col-12')[4].find('b').text

        return Status(
            device=device,
            name=content.find(class_='deviceName').text,
            temperature_in=int(_strip_unit(temp_in)),
            humidity_in=int(_strip_unit(humi_in)),
            temperature_out=int(_strip_unit(temp_out)),
            mode=mode_raw.strip(),
            co2_ppm=int(_strip_unit(co2_raw)),
        )
    except Exception as error:
        # XXX: Recuair sometimes return incorrectly formatted response.
        raise StatusError("Invalid response returned") from error


def main(argv: Optional[List[str]] = None) -> None:
    """Run the CLI."""
    options = docopt(__doc__, version=__version__, argv=argv)

    if options['--debug']:
        logging.basicConfig(level=logging.DEBUG,
                            format='%(asctime)s %(levelname)-8s %(name)s:%(funcName)s: %(message)s')

    for device in options['<device>']:
        try:
            status = get_status(device)
        except StatusError as error:
            print(error)
            sys.exit(1)
        print(status)


if __name__ == '__main__':
    main()
