"""Company discovery from authenticated CRM navigation (unofficial web format)."""
from types import SimpleNamespace
from urllib.parse import urljoin, urlparse, parse_qs
import httpx
from bs4 import BeautifulSoup
from dikidi.auth.flow import AuthFlow
from dikidi.catalog.service import CatalogService
from dikidi.core.config import NET_URL, BASE_URL, DEFAULT_USER_AGENT, DikidiConfig


class DiscoveryError(Exception):
    def __init__(self, stage):
        self.stage = stage
        super().__init__(stage)


def parse_companies(html, base_url=NET_URL):
    """Only links to the owner area; never treat arbitrary numeric IDs as companies."""
    result = {}
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.select("a[href]"):
        url = urlparse(urljoin(base_url, a["href"]))
        if url.scheme != 'https' or url.hostname not in (urlparse(NET_URL).hostname, urlparse(BASE_URL).hostname) or not url.path.startswith("/ru/owner/"):
            continue
        company_id = parse_qs(url.query).get("company", [""])[0]
        name = a.get_text(" ", strip=True)
        if company_id.isdigit() and name and company_id not in result:
            result[company_id] = name
    return result


class Discovery:
    def __init__(self, phone, password):
        self.phone = DikidiConfig(phone=phone, password=password, company_id='').clean_phone
        self.password = password
        self.client = httpx.Client(timeout=15, headers={"User-Agent": DEFAULT_USER_AGENT})
        self.companies = {}
        self.config = SimpleNamespace(company_id="")

    def login(self):
        # AuthFlow's company parameter is only used after authentication, for navigation.
        try:
            AuthFlow.login(self.client, self.phone, self.password, "")
        except Exception as exc:
            raise DiscoveryError('authentication') from exc
        try:
            # The journal requires a company. The business landing page lists
            # the authenticated user's projects before one is selected.
            response = self.client.get(f"{BASE_URL}/business/", follow_redirects=True)
            response.raise_for_status()
            self.companies = parse_companies(response.text, str(response.url))
        except Exception as exc:
            raise DiscoveryError('companies') from exc
        if not self.companies:
            raise DiscoveryError('companies')
        return self.companies

    def masters(self, company_id):
        if company_id not in self.companies:
            raise ValueError("Company not in authenticated account")
        self.config.company_id = company_id
        return {str(m.id): m.name for m in CatalogService(self).get_masters()
                if m.is_master}

    def get_ajax_headers(self, referer_path):
        headers = {"X-Requested-With": "XMLHttpRequest", "Origin": NET_URL,
                   "Referer": NET_URL + referer_path}
        for cookie in self.client.cookies.jar:
            if cookie.name == "XSRF-TOKEN":
                headers["X-XSRF-TOKEN"] = cookie.value
        return headers

    def request(self, method, url, **kwargs):
        response = self.client.request(method, url, **kwargs)
        response.raise_for_status()
        return response

    def close(self):
        self.client.close()
        self.password = ""
