from pathlib import Path
from unittest import TestCase
from unittest.mock import call, patch

import requests
import responses
from testfixtures import OutputCapture

from recuair_cli.main import Status, StatusError, get_status, main

_DATA = Path(__file__).parent / 'data'


class GetStatusTest(TestCase):
    def test(self):
        with responses.RequestsMock() as rsps:
            with open(_DATA / 'response.html', 'rb') as file:
                rsps.add(responses.GET, 'http://example/', body=file.read(), content_type="text/html")

            status = get_status('example')

            result = Status(device='example', name='Holly', temperature_in=17, humidity_in=56, temperature_out=5,
                            mode='AUTO', co2_ppm=1246)
            self.assertEqual(status, result)

    def test_error(self):
        with responses.RequestsMock() as rsps:
            rsps.add(responses.GET, 'http://example/', body=requests.RequestException('Gazpacho!'))

            with self.assertRaisesRegex(StatusError, 'Error fetching status of device example: Gazpacho!'):
                get_status('example')


class MainTest(TestCase):
    def test(self):
        status = Status(device='example', name='Holly', temperature_in=18, humidity_in=57, temperature_out=5,
                        mode='AUTO', co2_ppm=1232)
        with patch('recuair_cli.main.get_status', return_value=status) as get_status_mock:
            with OutputCapture() as output:
                main(['example'])

        self.assertEqual(get_status_mock.mock_calls, [call('example')])
        output.compare(f'{status}')

    def test_error(self):
        with patch('recuair_cli.main.get_status', side_effect=StatusError('Gazpacho!')):
            with OutputCapture() as output:
                with self.assertRaises(SystemExit):
                    main(['example'])

        output.compare('Gazpacho!')
