"""Compatibility fix for repeated service parameters in SDK 0.1.3."""
import secrets

from dikidi.appointments.service import AppointmentService
from dikidi.appointments.parser import parse_reservation_response
from dikidi.core.config import NET_URL


class MultiServiceAppointments(AppointmentService):
    def reserve_time(self, master_id, service_ids, time_str, unique_key=None):
        if not service_ids:
            raise ValueError('At least one service is required')
        key = unique_key or str(secrets.randbelow(90_000_000) + 10_000_000)
        # SDK 0.1.3 converts repeated (services_id[], id) pairs to a dict,
        # silently keeping only the last service. HTTPX encodes a list value
        # as repeated query parameters without losing any service IDs.
        params = {
            'company_id': self.company_id,
            'master_id': str(master_id),
            'time': time_str,
            'action_source_id': '3',
            'is-from-journal': '1',
            'unique_key': key,
            'services_id[]': [str(service_id) for service_id in service_ids],
        }
        headers = self.transport.get_ajax_headers(
            f'/ru/owner/clients/?company={self.company_id}')
        response = self.transport.request(
            'GET', f'{NET_URL}/ajax/newrecord/time_reservation/',
            headers=headers, params=params)
        response.raise_for_status()
        return parse_reservation_response(response.json(), unique_key=key)
