from types import SimpleNamespace

import httpx
import pytest

from app.dikidi.appointments import MultiServiceAppointments
from app.dikidi.sdk_client import SdkDikidiClient


@pytest.mark.parametrize('ids', [['11'], ['11', '12'], ['11', '12', '13']])
def test_all_services_reach_encoded_http_request(ids):
    captured = []
    def respond(request):
        captured.append(request)
        return httpx.Response(200, json={'record_id': '99'})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        transport = SimpleNamespace(
            config=SimpleNamespace(company_id='42'),
            get_ajax_headers=lambda path: {}, request=client.request)
        reservation = MultiServiceAppointments(transport).reserve_time(
            '7', ids, '2026-10-12 15:00:00', unique_key='test-key')
    assert len(captured) == 1
    assert captured[0].url.params.get_list('services_id[]') == ids
    assert captured[0].url.params['company_id'] == '42'
    assert captured[0].url.params['unique_key'] == reservation.unique_key
    assert reservation.record_id == '99'


def test_sdk_client_installs_compatibility_adapter(monkeypatch):
    import dikidi
    api = SimpleNamespace(transport=SimpleNamespace(config=SimpleNamespace(company_id='42')))
    monkeypatch.setattr(dikidi, 'DikidiAPI', lambda **kwargs: api)
    client = SdkDikidiClient('phone', 'secret', '42')
    assert isinstance(client._get_api().appointments, MultiServiceAppointments)
