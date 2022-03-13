import base64
from pathlib import Path
from typing import Dict

import requests.auth

from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry


class Client:
    """
    Abstract client to talk to Databricks
    """

    def __init__(self, api_url: str, api_token: str, endpoint: str):
        """
        :param api_url: The url that can be used to talk to the workspace
        :param api_token: Required auth token
        :param endpoint: Endpoint to construct base url
        """
        self._api_url = api_url
        self._api_token = api_token
        self._base_url = f"{self._api_url}/api/2.0/{endpoint}"

    def get_auth(self):
        """
        Get a BearerAuth for requests
        """
        # TODO(ML-12218): api_token expires in 24hrs or less; switch to credential provider
        return self.BearerAuth(self._api_token)

    @staticmethod
    def get_request_session() -> requests.Session:
        retry = Retry(
            total=6,
            # sleep between retries will be:
            #   {backoff factor} * (2 ** ({number of total retries} - 1))
            # so this will sleep for [5, 10, 20, 40, 80, 160..] seconds
            # which is a total of 315 seconds of wait time with 6 retries
            # which is a total of > 5 minutes of wait time for workspace / jobs
            # to restart or recover from downtime
            backoff_factor=5,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["GET", "POST"])

        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    class BearerAuth(requests.auth.AuthBase):
        def __init__(self, token: str):
            self._token = token

        def __call__(self, r):
            r.headers["authorization"] = f"Bearer {self._token}"
            return r


class WorkspaceClient(Client):
    """
    Client to talk to the workspace to read / write notebooks
    """
    _IMPORT_API = "/import"
    _EXPORT_API = "/export"
    _LIST_API = "/list"
    _MKDIRS_API = "/mkdirs"
    _DELETE_API = "/delete"

    def __init__(self, api_url: str, api_token: str):
        """
        :param api_url: The url that can be used to talk to the workspace
        :param api_token: Required auth token
        """
        super().__init__(api_url, api_token, "workspace")

    def import_source(self, path: str, local_path: str) -> None:
        with open(local_path, "rb") as fp:
            content = fp.read()
        self._import_notebook(path, content, "SOURCE")

    def _import_notebook(self, path: str, content: bytes, content_format: str) -> None:
        encoded_content = base64.standard_b64encode(content)
        data = {
            "path": path,
            "format": content_format,
            "language": "PYTHON",
            "content": encoded_content.decode(),
            "overwrite": "true",
        }

        with self.get_request_session() as s:
            resp = s.post(self._base_url + self._IMPORT_API,
                          json=data,
                          auth=self.get_auth(),
                          )

        if resp.status_code != 200:
            raise Exception(
                f"Unable to generate notebook at {path} using format {content_format}: {resp.text}")

    def export_source(self, path: str, local_path: Path):
        content = self._export_notebook(path, "SOURCE")
        with local_path.open("w") as fp:
            fp.write(content)

    def _export_notebook(self, path: str, content_format: str) -> str:
        data = {
            "path": path,
            "format": content_format,
        }

        with self.get_request_session() as s:
            resp = s.get(self._base_url + self._EXPORT_API, json=data, auth=self.get_auth())
        if resp.status_code != 200:
            raise Exception(
                f"Unable to export notebook at {path} using format {content_format}: {resp.text}")

        content_b64 = resp.json()["content"]
        return base64.standard_b64decode(content_b64).decode("utf-8")

    def mkdirs(self, path: str):
        data = {
            "path": path
        }
        with self.get_request_session() as s:
            resp = s.post(self._base_url + self._MKDIRS_API, json=data, auth=self.get_auth())
        if resp.status_code != 200:
            raise Exception(f"Unable to mkdirs {path}")

    def delete(self, path: str, recursive: bool = False):
        data = {
            "path": path,
            "recursive": recursive
        }
        with self.get_request_session() as s:
            resp = s.post(self._base_url + self._DELETE_API, json=data, auth=self.get_auth())
        if resp.status_code != 200:
            raise Exception(f"Unable to delete {path}")

    def list(self, path: str) -> Dict:
        data = {"path": path}
        with self.get_request_session() as s:
            resp = s.get(self._base_url + self._LIST_API, json=data, auth=self.get_auth())

        return resp.json()
