"""Manage recuair devices.

Usage: recuair-cli [options] status <device>...
       recuair-cli [options] start <device>...
       recuair-cli [options] stop <device>...
       recuair-cli [options] light <intensity> <red> <green> <blue> <device>...
       recuair-cli [options] light off <device>...
       recuair-cli -h | --help
       recuair-cli --version

Subcommands:
  status                print status of devices
  start                 start devices
  stop                  stop devices
  light                 change light

Options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --debug               print debug logs
"""
import logging
import sys
from typing import Any, Dict, List, NamedTuple, Optional

import requests
from bs4 import BeautifulSoup
from docopt import docopt

from recuair_cli import __version__

_LOGGER = logging.getLogger(__name__)


class RecuairError(Exception):
    """An error occured when managing the device."""


class Status(NamedTuple):
    """Represents device status.

    Attributes:
        device: Hostname of the device.
        name: Name of the device.
        temperature_in: Temperature inside in ˚C.
        humidity_in: Humidity inside in %.
        temperature_out: Temperature outside in °C.
        mode: Operating mode.
        co2_ppm: CO2 levels in ppm.
        filter: Filter used in %.
        fan: Fan speed in %.
        light: Light intensity, range 0-5.
    """

    device: str
    name: str
    temperature_in: int
    humidity_in: int
    temperature_out: int
    mode: str
    co2_ppm: int
    filter: int
    fan: int
    light: int


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
        raise RecuairError(f"Error fetching status of device {device}: {error}") from error
    _LOGGER.debug("Response [%s]: %s", response, response.text)

    try:
        content = BeautifulSoup(response.text, features="html.parser")
        container = content.find(class_='container')
        temperature_raw = container.find_all(class_='col-12')[1].find(class_='bigText').text
        in_data, _, temp_out = temperature_raw.strip().partition('%')
        temp_in, _, humi_in = in_data.strip().partition('/')
        mode_raw = container.find_all(class_='col-12')[3].find('span').text
        co2_raw = container.find_all(class_='col-12')[4].find('b').text
        filter_raw = container.find_all(class_='filterBox')[1].div['style'].partition(':')[2].partition('%')[0]
        fan_raw = container.find_all(class_='filterBox')[2].div['style'].partition(':')[2].partition('%')[0]
        light_raw = container.find(id='myRange')['value']

        return Status(
            device=device,
            name=content.find(class_='deviceName').text,
            temperature_in=int(_strip_unit(temp_in)),
            humidity_in=int(_strip_unit(humi_in)),
            temperature_out=int(_strip_unit(temp_out)),
            mode=mode_raw.strip(),
            co2_ppm=int(_strip_unit(co2_raw)),
            filter=100 - int(_strip_unit(filter_raw)),
            fan=100 - int(_strip_unit(fan_raw)),
            light=int(light_raw),
        )
    except Exception as error:
        # XXX: Recuair sometimes return incorrectly formatted response.
        raise RecuairError(f"Invalid response returned from device {device}") from error


def post_request(device: str, data: Dict[str, Any]) -> None:
    """Send a POST request to the device."""
    try:
        # XXX: Disable redirects. Recuair returns 301 for POST requests.
        response = requests.post(f'http://{device}/', data=data, timeout=30, allow_redirects=False)
        response.raise_for_status()
    except requests.RequestException as error:
        _LOGGER.debug("Error encountered: %s", error)
        raise RecuairError(f"Error from device {device}: {error}") from error
    if response.status_code != 301:
        raise RecuairError(f"Unknown error from device {device}")
    # XXX: When invalid request is send, Recuair returns status page :-/
    _LOGGER.debug("Response [%s]: %s", response, response.text)


def main(argv: Optional[List[str]] = None) -> None:
    """Run the CLI."""
    options = docopt(__doc__, version=__version__, argv=argv)

    if options['--debug']:
        logging.basicConfig(level=logging.DEBUG,
                            format='%(asctime)s %(levelname)-8s %(name)s:%(funcName)s: %(message)s')

    error_found = False
    for device in options['<device>']:
        try:
            if options['start']:
                # XXX: Start in auto mode. Recuair GUI starts on mode 1.
                post_request(device, {'mode': 'auto'})
            elif options['stop']:
                post_request(device, {'mode': 'off'})
            elif options['light']:
                # XXX: Recuair doesn't accept only change in light intensity. Whole light setting has to be provided.
                if options['off']:
                    post_request(device, {'r': '0', 'g': '0', 'b': '0', 'intensity': '0'})
                else:
                    data = {'r': options['<red>'], 'g': options['<green>'], 'b': options['<blue>'],
                            'intensity': options['<intensity>']}
                    post_request(device, data)
            else:
                status = get_status(device)
                print(status)
        except RecuairError as error:
            print(error)
            error_found = True
    if error_found:
        sys.exit(1)


if __name__ == '__main__':
    main()
