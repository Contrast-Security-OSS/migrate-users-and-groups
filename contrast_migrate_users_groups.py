import argparse
import logging
import sys
from collections.abc import Iterable
from enum import IntEnum

from contrast_api import ContrastTeamServer, contrast_instance_from_json, load_config

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__file__)

try:
    from voluptuous import All, Length, Optional, Schema, Url
except ImportError:
    logger.fatal("voluptuous module is not installed (see README)")
    exit(1)

try:
    import inquirer
except ImportError:
    logger.fatal("inquirer module is not installed (see README")
    exit(1)

try:
    from rich.console import Console
    from rich.table import Table
except ImportError:
    logger.fatal("rich module is not installed (see README")
    exit(1)

args_parser = argparse.ArgumentParser()
args_parser.add_argument(
    "-c",
    "--config_file",
    "--config-file",
    help="Path to JSON config or - to read it from stdin, defaults to config.json",
    default="config.json",
    type=argparse.FileType("r"),
)

args = args_parser.parse_args()
config_schema = Schema(
    {
        "source": All(
            {
                "teamserverUrl": Url(),
                "apiKey": All(str, Length(1)),
                "authorizationHeader": All(str, Length(1)),
                "orgId": All(str, Length(1)),
                Optional("name", default="source"): str,
            },
            required=True,
        ),
        "destination": All(
            {
                "teamserverUrl": Url(),
                "apiKey": All(str, Length(1)),
                "authorizationHeader": All(str, Length(1)),
                "orgId": All(str, Length(1)),
                Optional("name", default="destination"): str,
            },
            required=True,
        ),
    },
)
config = load_config(schema=config_schema, file=args.config_file)

donor = contrast_instance_from_json(config["source"])
donor_org = config["source"]["orgId"]
recipient = contrast_instance_from_json(config["destination"])
recipient_org = config["destination"]["orgId"]

instances = [donor, recipient]

for instance in instances:
    print(f"testing connection with instance '{instance._name}'")
    connection_ok = False
    try:
        connection_ok = instance.test_connection()
    except Exception as e:
        print(e)
        sys.exit(-1)

    if not connection_ok:
        sys.exit(-1)

logger.info("Listing users")
source_users = donor.list_org_users(donor_org)
dest_users = recipient.list_org_users(recipient_org)


def create_user(instance: ContrastTeamServer, org_id: str, existing_user: dict):
    resp = instance.api_request(
        f"{org_id}/users",
        "POST",
        {
            "enabled": existing_user["enabled"],
            "api_only": existing_user["api_only"],
            "username": existing_user["user_uid"],
            "first_name": existing_user["first_name"],
            "last_name": existing_user["last_name"],
            "date_format": existing_user["preferences"]["date_format"],
            "time_format": existing_user["preferences"]["time_format"],
            "time_zone": existing_user["preferences"]["time_zone"],
            "role": existing_user["role"]["group_id"],
            "protect": existing_user["rasp_enabled"],
            "groups": [],
        },
    )

    if not resp.get("success", False):
        print(resp)
        exit(1)


console = Console()


def print_table(title: str, column: str, rows: Iterable[str]):
    table = Table(title=title)
    table.add_column(column, justify="center")
    for row in rows:
        table.add_row(row)

    console.print(table)


source_users_set = set(map(lambda user: user["user_uid"], source_users))
dest_users_set = set(map(lambda user: user["user_uid"], dest_users))

users_to_create = set(source_users_set - dest_users_set)

existing_users_in_dest = source_users_set & dest_users_set
if existing_users_in_dest:
    print_table("Users already in source and dest", "Username", existing_users_in_dest)

if not users_to_create:
    print("No users missing in destination")
else:
    print_table("Users to create", "Username", users_to_create)
    if not inquirer.confirm("Okay to create user(s)?"):
        exit(1)

for user in source_users:
    if user["user_uid"] in users_to_create:
        print(f"Creating user '{user['user_uid']}'")
        create_user(recipient, recipient_org, user)

logger.info("Listing groups and their users")
source_groups = donor.list_org_groups(donor_org)
groups_users = {}
for group in source_groups:
    group_id, group_name = group["group_id"], group["name"]
    users = donor.list_group_users(donor_org, group_id=group_id)
    groups_users[group_name] = list(
        map(lambda user: user["uid"], users["group"]["users"])
    )

dest_groups = recipient.list_org_groups(recipient_org)
source_groups_set = set(map(lambda group: group["name"], source_groups))
dest_groups_set = set(map(lambda group: group["name"], dest_groups))
groups_to_create = set(source_groups_set - dest_groups_set)

existing_groups_in_dest = source_groups_set & dest_groups_set
if existing_groups_in_dest:
    print_table("Groups already in source and dest", "Group", existing_groups_in_dest)

if not groups_to_create:
    print("No groups missing in destination")
else:
    print_table("Groups to create", "Group", groups_to_create)
    if not inquirer.confirm("Okay to create group(s)?"):
        exit(1)


def create_group(
    instance: ContrastTeamServer,
    org_id: str,
    name: str,
    users: list[str],
    onboard_role: str,
):
    path = f"{org_id}/groups"
    resp = instance.api_request(
        path,
        "POST",
        {
            "scope": {"app_scope": {"onboard_role": onboard_role, "exceptions": []}},
            "name": name,
            "users": users,
        },
    )

    if not resp.get("success", False):
        print(resp)
        exit(1)


class Roles(IntEnum):
    ADMIN = 4
    RULES_ADMIN = 3
    EDIT = 2
    VIEW = 1


for group in source_groups:
    if group["name"] in groups_to_create:
        role = group.get("role")
        if not role:
            role = min(
                map(
                    lambda application: Roles.__members__[application["role"].upper()],
                    group["applications"],
                )
            )
            role = role.name.lower()

        print(
            f"Creating group '{group['name']}' with role '{role}' and member(s): {','.join(groups_users[group['name']])}"
        )

        create_group(
            recipient,
            recipient_org,
            group["name"],
            groups_users[group["name"]],
            role,
        )
