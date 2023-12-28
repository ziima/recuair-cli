from pathlib import Path
from unittest import TestCase
from unittest.mock import call, patch

import requests
import responses
from responses.matchers import urlencoded_params_matcher
from testfixtures import OutputCapture

from recuair_cli.main import RecuairError, Status, get_status, main, post_request

_DATA = Path(__file__).parent / 'data'


class GetStatusTest(TestCase):
    def test(self):
        with responses.RequestsMock() as rsps:
            with open(_DATA / 'response.html', 'rb') as file:
                rsps.add(responses.GET, 'http://example/', body=file.read(), content_type="text/html")

            status = get_status('example')

            result = Status(device='example', name='Holly', temperature_in=17, humidity_in=56, temperature_out=5,
                            mode='AUTO', co2_ppm=1246, filter=2, fan=69, light=5)
            self.assertEqual(status, result)

    def test_invalid(self):
        # Test case with '%%content%%' in the response.
        with responses.RequestsMock() as rsps:
            with open(_DATA / 'invalid.html', 'rb') as file:
                rsps.add(responses.GET, 'http://example/', body=file.read(), content_type="text/html")

            with self.assertRaisesRegex(RecuairError, 'Invalid response returned'):
                get_status('example')

    def test_error(self):
        with responses.RequestsMock() as rsps:
            rsps.add(responses.GET, 'http://example/', body=requests.RequestException('Gazpacho!'))

            with self.assertRaisesRegex(RecuairError, 'Error fetching status of device example: Gazpacho!'):
                get_status('example')


class PostRequestTest(TestCase):
    def test(self):
        with responses.RequestsMock() as rsps:
            rsps.add(responses.POST, 'http://example/', status=301, match=[urlencoded_params_matcher({"answer": "42"})])

            post_request('example', {'answer': '42'})

    def test_error(self):
        with responses.RequestsMock() as rsps:
            rsps.add(responses.POST, 'http://example/', body=requests.RequestException('Gazpacho!'))

            with self.assertRaisesRegex(RecuairError, 'Error from device example: Gazpacho!'):
                post_request('example', {'answer': '42'})


class MainTest(TestCase):
    def test_status(self):
        status = Status(device='example', name='Holly', temperature_in=18, humidity_in=57, temperature_out=5,
                        mode='AUTO', co2_ppm=1232, filter=0, fan=0, light=0)
        with patch('recuair_cli.main.get_status', return_value=status) as get_status_mock:
            with OutputCapture() as output:
                main(['status', 'example'])

        self.assertEqual(get_status_mock.mock_calls, [call('example')])
        output.compare(f'{status}')

    def test_start(self):
        with patch('recuair_cli.main.post_request') as post_request_mock:
            main(['start', 'example'])

        self.assertEqual(post_request_mock.mock_calls, [call('example', {'mode': 'auto'})])

    def test_stop(self):
        with patch('recuair_cli.main.post_request') as post_request_mock:
            main(['stop', 'example'])

        self.assertEqual(post_request_mock.mock_calls, [call('example', {'mode': 'off'})])

    def test_light(self):
        with patch('recuair_cli.main.post_request') as post_request_mock:
            main(['light', '5', '255', '110', '20', 'example'])

        self.assertEqual(post_request_mock.mock_calls,
                         [call('example', {'r': '255', 'g': '110', 'b': '20', 'intensity': '5'})])

    def test_light_off(self):
        with patch('recuair_cli.main.post_request') as post_request_mock:
            main(['light', 'off', 'example'])

        self.assertEqual(post_request_mock.mock_calls,
                         [call('example', {'r': '0', 'g': '0', 'b': '0', 'intensity': '0'})])

    def test_error(self):
        with patch('recuair_cli.main.get_status', side_effect=RecuairError('Gazpacho!')):
            with OutputCapture() as output:
                with self.assertRaises(SystemExit):
                    main(['status', 'example'])

        output.compare('Gazpacho!')
