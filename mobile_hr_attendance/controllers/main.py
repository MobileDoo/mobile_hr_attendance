from odoo import _, http
from odoo.http import request

from odoo.addons.mobile_connector.controllers.utils import MobileApiError, mobile_route, require_access


class MobileAttendanceController(http.Controller):
    """Check in/out. History lists go through `/mobile/api/v1/records/attendance/list`."""

    @mobile_route('/mobile/api/v1/attendance/status')
    def status(self, payload):
        require_access('attendance', 'history')
        return request.env['mobile.attendance.service']._mobile_status()

    @mobile_route('/mobile/api/v1/attendance/check', idempotent=True)
    def check(self, payload):
        require_access('attendance', 'check')
        try:
            latitude = float(payload['latitude']) if payload.get('latitude') is not None else False
            longitude = float(payload['longitude']) if payload.get('longitude') is not None else False
        except (TypeError, ValueError):
            raise MobileApiError('bad_request', 'latitude/longitude must be numbers')
        reason_id = payload.get('reason_id')
        if reason_id is not None and not isinstance(reason_id, int):
            raise MobileApiError('bad_request', 'reason_id must be an id')
        try:
            accuracy = float(payload['accuracy']) if payload.get('accuracy') is not None else None
        except (TypeError, ValueError):
            raise MobileApiError('bad_request', 'accuracy must be a number (metres)')
        return request.env['mobile.attendance.service']._mobile_check(
            self._geo(latitude, longitude), photo=payload.get('photo'), reason_id=reason_id,
            accuracy=accuracy, mock=bool(payload.get('mock')), at=self._at(payload))

    def _at(self, payload):
        """When the person pressed the button, if the request was kept on the phone meanwhile (unix seconds)."""
        if payload.get('at') is None:
            return None
        try:
            return float(payload['at'])
        except (TypeError, ValueError):
            raise MobileApiError('bad_request', 'at must be a unix time in seconds')

    def _geo(self, latitude, longitude):
        """Same keys as hr_attendance's `_get_geoip_response` (stored in in_*/out_* fields)."""
        geo = {
            'mode': 'systray',
            'latitude': latitude,
            'longitude': longitude,
            'ip_address': request.httprequest.remote_addr,
            'browser': 'MobileDoo',
            'city': _('Unknown'),
            'country_name': _('Unknown'),
        }
        try:
            geoip = request.geoip
            geo['city'] = geoip.city.name or geo['city']
            geo['country_name'] = geoip.country.name or geoip.continent.name or geo['country_name']
        except Exception:  # no GeoIP database installed
            pass
        return geo
