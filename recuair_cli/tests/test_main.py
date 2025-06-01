from http import HTTPStatus
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import call, patch

import httpx
import respx
from httpx import HTTPError, Response
from testfixtures import Comparison, OutputCapture

from recuair_cli.main import RecuairError, Status, get_status, main, post_request

_DATA = Path(__file__).parent / "data"


class GetStatusTest(IsolatedAsyncioTestCase):
    async def test(self):
        # Test response.
        with respx.mock() as rsps:
            with open(_DATA / "response.html", "rb") as file:
                rsps.get("http://example/").mock(Response(200, content=file.read()))

            async with httpx.AsyncClient() as client:
                status = await get_status(client, "example")

            result = Status(
                device="example",
                name="Holly",
                temperature_in=17,
                humidity_in=56,
                temperature_out=5,
                mode="AUTO",
                co2_ppm=1246,
                filter=2,
                fan=69,
                light=5,
            )
            self.assertEqual(status, result)

    async def test_off(self):
        # Test response from stopped device
        with respx.mock() as rsps:
            with open(_DATA / "response-off.html", "rb") as file:
                rsps.get("http://example/").mock(Response(200, content=file.read()))

            async with httpx.AsyncClient() as client:
                status = await get_status(client, "example")

            result = Status(
                device="example",
                name="Holly",
                temperature_in=None,
                humidity_in=None,
                temperature_out=None,
                mode="AUTO",
                co2_ppm=None,
                filter=2,
                fan=69,
                light=5,
            )
            self.assertEqual(status, result)

    async def test_warning(self):
        # Test response with warnings.
        with respx.mock() as rsps:
            with open(_DATA / "warning.html", "rb") as file:
                rsps.get("http://example/").mock(Response(200, content=file.read()))

            async with httpx.AsyncClient() as client:
                status = await get_status(client, "example")

            result = Status(
                device="example",
                name="Holly",
                temperature_in=None,
                humidity_in=None,
                temperature_out=None,
                mode="Off",
                co2_ppm=None,
                filter=100,
                fan=0,
                light=0,
                warnings=["N3: Filtry - KONEC životnosti, prosím vyměňte filtry"],
            )
            self.assertEqual(status, result)

    async def test_invalid(self):
        # Test case with '%%content%%' in the response.
        with respx.mock() as rsps:
            with open(_DATA / "invalid.html", "rb") as file:
                rsps.get("http://example/").mock(Response(200, content=file.read()))

            with self.assertRaisesRegex(RecuairError, "Invalid response returned"):
                async with httpx.AsyncClient() as client:
                    await get_status(client, "example")

    async def test_error(self):
        with respx.mock() as rsps:
            rsps.get("http://example/").mock(side_effect=HTTPError("Gazpacho!"))

            with self.assertRaisesRegex(
                RecuairError, "Error fetching status of device example: HTTPError.*Gazpacho!.*"
            ):
                async with httpx.AsyncClient() as client:
                    await get_status(client, "example")


class PostRequestTest(IsolatedAsyncioTestCase):
    async def test(self):
        with respx.mock() as rsps:
            rsps.post("http://example/", data={"answer": "42"}).mock(Response(HTTPStatus.SEE_OTHER))

            async with httpx.AsyncClient() as client:
                await post_request(client, "example", {"answer": "42"})

    async def test_fw_12(self):
        # Test post to firmware 12
        with respx.mock() as rsps:
            rsps.post("http://example/", data={"answer": "42"}).mock(Response(HTTPStatus.MOVED_PERMANENTLY))

            async with httpx.AsyncClient() as client:
                await post_request(client, "example", {"answer": "42"})

    async def test_error(self):
        with respx.mock() as rsps:
            rsps.post("http://example/").mock(side_effect=HTTPError("Gazpacho!"))

            with self.assertRaisesRegex(RecuairError, "Error from device example: Gazpacho!"):
                async with httpx.AsyncClient() as client:
                    await post_request(client, "example", {"answer": "42"})

    async def test_invalid(self):
        # Test recuair returns 200 response on invalid requests.
        with respx.mock() as rsps:
            rsps.post("http://example/").mock(Response(200, text="status"))

            with self.assertRaisesRegex(RecuairError, "Unknown error from device example"):
                async with httpx.AsyncClient() as client:
                    await post_request(client, "example", {"answer": "42"})


class MainTest(TestCase):
    def test_status(self):
        status = Status(
            device="example",
            name="Holly",
            temperature_in=18,
            humidity_in=57,
            temperature_out=5,
            mode="AUTO",
            co2_ppm=1232,
            filter=0,
            fan=0,
            light=0,
        )
        with patch("recuair_cli.main.get_status", return_value=status) as get_status_mock:
            with OutputCapture() as output:
                main(["status", "example"])

        self.assertEqual(get_status_mock.mock_calls, [call(Comparison(httpx.AsyncClient), "example")])
        output.compare(f"{status}")

    def test_start(self):
        with patch("recuair_cli.main.post_request", return_value=None) as post_request_mock:
            main(["start", "example"])

        self.assertEqual(
            post_request_mock.mock_calls, [call(Comparison(httpx.AsyncClient), "example", {"mode": "auto"})]
        )

    def test_stop(self):
        with patch("recuair_cli.main.post_request", return_value=None) as post_request_mock:
            main(["stop", "example"])

        self.assertEqual(
            post_request_mock.mock_calls, [call(Comparison(httpx.AsyncClient), "example", {"mode": "off"})]
        )

    def test_holiday(self):
        with patch("recuair_cli.main.post_request", return_value=None) as post_request_mock:
            main(["holiday", "example"])

        self.assertEqual(
            post_request_mock.mock_calls, [call(Comparison(httpx.AsyncClient), "example", {"mode": "holiday"})]
        )

    def test_bypass(self):
        with patch("recuair_cli.main.post_request", return_value=None) as post_request_mock:
            main(["bypass", "example"])

        self.assertEqual(
            post_request_mock.mock_calls, [call(Comparison(httpx.AsyncClient), "example", {"mode": "bypass"})]
        )

    def test_light(self):
        with patch("recuair_cli.main.post_request", return_value=None) as post_request_mock:
            main(["light", "5", "255", "110", "20", "example"])

        self.assertEqual(
            post_request_mock.mock_calls,
            [call(Comparison(httpx.AsyncClient), "example", {"r": "255", "g": "110", "b": "20", "intensity": "5"})],
        )

    def test_light_off(self):
        with patch("recuair_cli.main.post_request", return_value=None) as post_request_mock:
            main(["light", "off", "example"])

        self.assertEqual(
            post_request_mock.mock_calls,
            [call(Comparison(httpx.AsyncClient), "example", {"r": "0", "g": "0", "b": "0", "intensity": "0"})],
        )

    def test_reset_filters(self):
        with patch("recuair_cli.main.post_request", return_value=None) as post_request_mock:
            main(["reset-filters", "example"])

        self.assertEqual(
            post_request_mock.mock_calls,
            [call(Comparison(httpx.AsyncClient), "example", {"filterNotification": "1"})],
        )

    def test_error(self):
        def _wrap_noop(func):
            return func

        with patch("recuair_cli.main.get_status", side_effect=RecuairError("Gazpacho!")):
            with patch("recuair_cli.main._wrap_retry", new=_wrap_noop):
                with OutputCapture() as output:
                    with self.assertRaises(SystemExit):
                        main(["status", "example"])

        output.compare("Gazpacho!")
