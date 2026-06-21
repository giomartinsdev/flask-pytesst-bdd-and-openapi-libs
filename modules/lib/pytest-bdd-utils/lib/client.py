import json
from flask.testing import FlaskClient


class BDDClient:
    def __init__(self, client: FlaskClient):
        self._client = client

    def get(self, path: str, **kwargs):
        return self._client.get(path, **kwargs)

    def json_post(self, path: str, body: dict):
        return self._client.post(path, data=json.dumps(body), content_type="application/json")

    def json_put(self, path: str, body: dict):
        return self._client.put(path, data=json.dumps(body), content_type="application/json")

    def json_patch(self, path: str, body: dict):
        return self._client.patch(path, data=json.dumps(body), content_type="application/json")

    def delete(self, path: str):
        return self._client.delete(path)
