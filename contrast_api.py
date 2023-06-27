import json
import logging
import os
from json import JSONDecodeError
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__file__)

try:
    import glom
except ImportError:
    logger.fatal("glom module is not installed (see README)")
    exit(1)

try:
    import requests
except ImportError:
    logger.fatal("requests module is not installed (see README)")
    exit(1)


try:
    from voluptuous import All, Length, Schema, Url
    from voluptuous.error import MultipleInvalid
except ImportError:
    logger.fatal("voluptuous module is not installed (see README)")
    exit(1)

config_schema = Schema(
    {
        "environments": All(
            [
                {
                    "name": All(str, Length(1)),
                    "teamserverUrl": Url(),
                    "apiKey": All(str, Length(1)),
                    "authorizationHeader": All(str, Length(1)),
                    "orgId": All(str, Length(1)),
                }
            ],
            Length(1),
            required=True,
        )
    },
    required=True,
)


def load_config(
    file_path="config.json", schema: Schema = config_schema, file=None
) -> dict[str, dict]:
    try:
        if file:
            config = json.load(file)
            file.close()
        else:
            try:
                with open(file_path) as config:
                    config = json.load(config)
            except OSError as e:
                logger.error("Could not load config", e)
                exit(1)
    except JSONDecodeError as e:
        logger.error("Could not decode JSON from config", e)
        exit(1)

    # Validate environments in the config.json have expected keys
    try:
        config = schema(config)
    except MultipleInvalid as e:
        logger.error("config invalid - " + str(e))
        for error in e.errors:
            logger.error(f"\t{error.path[0]}: {error.msg}")
        exit(1)

    return config


def load_config_from_env() -> dict[str, str]:
    """Validate configuration has been supplied by environment variables."""
    config_schema = Schema(
        {
            "CONTRAST__API__URL": Url(),  # type: ignore
            "CONTRAST__API__API_KEY": All(Length(1)),
            "CONTRAST__API__AUTH_HEADER": All(str, Length(1)),
        }
    )
    environment_config = {k: os.getenv(k) for (k) in config_schema.schema.keys()}

    try:
        config_schema(environment_config)
    except MultipleInvalid as e:
        logger.error("ERROR: configuration invalid, check environment variables:")
        for error in e.errors:
            logger.error(f"\t{error.path[0]}: {error.msg}")
        exit(1)

    return environment_config  # type: ignore


class ContrastTeamServer:
    def __init__(
        self, teamserver_url, api_key, authorization_header, org_uuid, name=None
    ):
        self._teamserver_url = teamserver_url
        self._api_key = api_key
        self._authorization_header = authorization_header
        self._org_uuid = org_uuid
        self._name = name

        self._is_superadmin = False
        self._connection_checked = False
        self._skip_certificate_validation = False
        if "INSECURE_SKIP_CERT_VALIDATION" in os.environ:
            self._skip_certificate_validation = os.environ[
                "INSECURE_SKIP_CERT_VALIDATION"
            ].lower() in ("1", "true")

        self._title_cwe_cache = {}

    def request_headers(self, api_key) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Api-Key": api_key,
            "Authorization": self._authorization_header,
            "Content-Type": "application/json",
        }

    def api_request(
        self,
        path: str,
        method: str = "GET",
        body: Any | None = None,
        should_retry: bool = False,
        api_key: str | None = None,
    ):
        """
        Make a HTTP request to TeamServer.
        Raises :class:`HTTPError`, if one occurred (after retrying, if `should_retry` is True).

        :param path: URI for the request.
        :param method: method for the Request: ``GET``, ``OPTIONS``, ``HEAD``, ``POST``, ``PUT``, ``PATCH``, or ``DELETE``.
        :param body: (optional) A JSON serializable Python object to send in the body of the Request.
        :param should_retry: Boolean. Enable/disable retrying when an exception occurs with the request.
        :param api_key: (optional) TeamServer API key if you wish to override the class `api_key`.
        :return: JSON body of the response.
        """
        if not self._connection_checked and path != "profile":
            self.test_connection()

        logger.debug(method + " " + path)
        if api_key is None:
            api_key = self._api_key

        response = requests.request(
            method,
            self._teamserver_url + path,
            headers=self.request_headers(api_key),
            json=body,
            verify=not self._skip_certificate_validation,
        )
        if should_retry:
            retry_count = 0
            while retry_count < 2:
                try:
                    response.raise_for_status()
                    return response.json()
                except Exception as e:
                    if retry_count < 2:
                        retry_count += 1
                        response = requests.request(
                            method,
                            self._teamserver_url + path,
                            headers=self.request_headers(api_key),
                            json=body,
                            verify=not self._skip_certificate_validation,
                        )
                    else:
                        raise e

        return response.json()

    def paginate_through_all(
        self, path, response_key, api_key, body=None, method="GET"
    ):
        """Helper to retrieve all pages of a paginated call."""
        output = []

        call = path
        offset = 0
        more = True

        while more:
            url = f"{call}&offset={offset}"
            response = self.api_request(
                url, method, body, should_retry=True, api_key=api_key
            )

            new_page = glom.glom(response, response_key)
            output.extend(new_page)
            count = len(new_page)

            offset += count
            more = count > 0

        return output

    def list_orgs(self):
        """Superadmin API call to retrieve all organizations."""
        if self._is_superadmin:
            # fetch both and return only those we are allowed to access, as access could be limited for this specific user
            all_orgs = self.api_request("superadmin/organizations?limit=100")[
                "organizations"
            ]
            profile_orgs = self.api_request("profile/organizations")["organizations"]
            allowed_orgs_ids = list(
                map(lambda org: org["organization_uuid"], profile_orgs)
            )

            orgs_allowed_access_to = (
                org for org in all_orgs if org["organization_uuid"] in allowed_orgs_ids
            )
            return orgs_allowed_access_to

        return self.api_request("profile/organizations")["organizations"]

    def list_org_users(self, org_id, api_key=None):
        """Organization specific API call to list all users."""
        return self.paginate_through_all(
            f"{org_id}/users?expand=preferences,role,skip_links&limit=100",
            "users",
            api_key=api_key,
        )

    def list_org_groups(self, org_id, api_key=None):
        """Organization specific API call to list all groups."""
        return self.paginate_through_all(
            f"{org_id}/groups?expand=applications,skip_links",
            "custom_groups.groups",
            api_key=api_key,
        )

    def list_group_users(self, org_id, group_id, api_key=None):
        """Organization specific API call to list users in a group."""
        return self.api_request(f"{org_id}/groups/{group_id}/users", api_key=api_key)

    def test_connection(self):
        """Check TeamServer Connection and Credentials."""
        try:
            response = self.api_request("profile")
        except JSONDecodeError as e:
            logger.error("Profile check failed - check credentials: ", e)
            return False
        if "success" in response and not response["success"]:
            logger.error("Profile check failed - check credentials: ", response)
            return False
        self._connection_checked = True

        if "superadmin_role" not in response["user"] or (
            "superadmin_role" in response["user"]
            and response["user"]["superadmin_role"]
            not in ("SUPERADMIN", "SERVER_ADMIN")
        ):
            self._is_superadmin = False
            return True

        self._is_superadmin = True
        return True


def contrast_instance_from_json(json: dict) -> ContrastTeamServer:
    url = json["teamserverUrl"]
    url_parts = urlparse(url)
    if url_parts.path != "/Contrast/api/ng/":
        url = f"{url_parts.scheme}://{url_parts.netloc}/Contrast/api/ng/"

    logger.debug(f"Base URL: {url}")

    return ContrastTeamServer(
        url,
        json["apiKey"],
        json["authorizationHeader"],
        json["orgId"],
        json.get("name"),
    )
