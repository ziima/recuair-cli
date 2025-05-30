"""Manage recuair devices.

Usage: recuair-cli [options] status <device>...
       recuair-cli [options] start <device>...
       recuair-cli [options] stop <device>...
       recuair-cli [options] holiday <device>...
       recuair-cli [options] bypass <device>...
       recuair-cli [options] light <intensity> <red> <green> <blue> <device>...
       recuair-cli [options] light off <device>...
       recuair-cli -h | --help
       recuair-cli --version

Subcommands:
  status                print status of devices
  start                 start devices
  stop                  stop devices
  holiday               set holiday mode
  bypass                set bypass mode
  light                 change light

Options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --debug               print debug logs
"""

import asyncio
import logging
import sys
from collections.abc import Coroutine
from http import HTTPStatus
from typing import Any, Callable, NamedTuple, Optional, TypeVar, cast

import httpx
from bs4 import BeautifulSoup, PageElement, Tag
from docopt import docopt
from tenacity import retry, stop_after_attempt, wait_exponential

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
    return value.strip().partition(" ")[0]


async def get_status(client: httpx.AsyncClient, device: str) -> Status:
    """Return device status."""
    try:
        response = await client.get(f"http://{device}/", timeout=3)
        response.raise_for_status()
    except httpx.HTTPError as error:
        _LOGGER.debug("Error encountered: %s", error)
        raise RecuairError(f"Error fetching status of device {device}: {error!r}") from error
    _LOGGER.debug("Response [%s]: %s", response, response.text)

    try:
        content = BeautifulSoup(response.text, features="html.parser")
        container = cast(Tag, content.find(class_="container"))
        temperature_raw = cast(
            PageElement, cast(Tag, container.find_all(class_="col-12")[1]).find(class_="bigText")
        ).text
        in_data, _, temp_out = temperature_raw.strip().partition("%")
        temp_in, _, humi_in = in_data.strip().partition("/")
        mode_raw = cast(PageElement, cast(Tag, container.find_all(class_="col-12")[3]).find("span")).text
        co2_raw = cast(PageElement, cast(Tag, container.find_all(class_="col-12")[4]).find("b")).text
        filter_raw = (
            cast(
                str,
                cast(Tag, cast(Tag, container.find_all(class_="filterBox")[1]).div)["style"],
            )
            .partition(":")[2]
            .partition("%")[0]
        )
        fan_raw = (
            cast(
                str,
                cast(Tag, cast(Tag, container.find_all(class_="filterBox")[2]).div)["style"],
            )
            .partition(":")[2]
            .partition("%")[0]
        )
        light_raw = cast(str, cast(Tag, container.find(id="myRange"))["value"])

        return Status(
            device=device,
            name=cast(Tag, content.find(class_="deviceName")).text,
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


async def post_request(client: httpx.AsyncClient, device: str, data: dict[str, Any]) -> None:
    """Send a POST request to the device."""
    try:
        # XXX: Disable redirects. Recuair returns 301 for POST requests.
        response = await client.post(f"http://{device}/", data=data, timeout=5, follow_redirects=False)
    except httpx.HTTPError as error:
        _LOGGER.debug("Error encountered: %s", error)
        raise RecuairError(f"Error from device {device}: {error}") from error
    if response.status_code != HTTPStatus.MOVED_PERMANENTLY:
        raise RecuairError(f"Unknown error from device {device}, status code {response.status_code}")
    # XXX: When invalid request is send, Recuair returns status page :-/
    _LOGGER.debug("Response [%s]: %s", response, response.text)


X = TypeVar("X")


# XXX: Add retry, recuair devices are often irresponsive.
def _wrap_retry(func: Callable[..., X]) -> Callable[..., X]:
    return retry(reraise=True, stop=stop_after_attempt(10), wait=wait_exponential(max=30))(func)


async def _run(options: dict[str, str]) -> None:  # noqa: C901
    """Actually run the command."""
    error_found = False
    async with httpx.AsyncClient() as client:
        coros: list[Coroutine] = []
        for device in options["<device>"]:
            if options["start"]:
                # XXX: Start in auto mode. Recuair GUI starts on mode 1.
                coros.append(_wrap_retry(post_request)(client, device, {"mode": "auto"}))
            elif options["stop"]:
                coros.append(_wrap_retry(post_request)(client, device, {"mode": "off"}))
            elif options["holiday"]:
                coros.append(_wrap_retry(post_request)(client, device, {"mode": "holiday"}))
            elif options["bypass"]:
                coros.append(_wrap_retry(post_request)(client, device, {"mode": "bypass"}))
            elif options["light"]:
                # XXX: Recuair doesn't accept only change in light intensity.
                # Whole light setting has to be provided.
                if options["off"]:
                    coros.append(
                        _wrap_retry(post_request)(client, device, {"r": "0", "g": "0", "b": "0", "intensity": "0"})
                    )
                else:
                    data = {
                        "r": options["<red>"],
                        "g": options["<green>"],
                        "b": options["<blue>"],
                        "intensity": options["<intensity>"],
                    }
                    coros.append(_wrap_retry(post_request)(client, device, data))
            else:
                coros.append(_wrap_retry(get_status)(client, device))

        error_found = False
        for result in await asyncio.gather(*coros, return_exceptions=True):
            if isinstance(result, BaseException):
                print(result)
                error_found = True
            elif result:
                print(result)

    if error_found:
        sys.exit(1)


def main(argv: Optional[list[str]] = None) -> None:
    """Run the CLI."""
    options = docopt(__doc__, version=__version__, argv=argv)

    if options["--debug"]:  # pragma: no cover
        logging.basicConfig(
            level=logging.DEBUG, format="%(asctime)s %(levelname)-8s %(name)s:%(funcName)s: %(message)s"
        )

    asyncio.run(_run(options))


if __name__ == "__main__":  # pragma: no cover
    main()
