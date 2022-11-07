# Contrast Users & Groups Migrator

Script to migrate users and groups from one instance/organization to another.

Groups will be created with the **applications onboarded to group** option, and the role from the source instance.
If there are several roles used within one group, the least priviliged one will be selected (View < Edit < Rules Admin < Admin).

Application entries will not be added to any newly created groups in the destination. Agents should use the `application.group` configuration to ensure applications are added to the groups when reporting into the new instance.

## Requirements
- Python 3.10 (other versions _may_ work but are untested)
- Ability to install Python libraries from `requirements.txt`

## Setup
You can run this script locally with a Python install, or, in a container with the provided `Dockerfile`

### Container use

#### Pre-built
```bash
docker run -it -v $PWD/config.json:/usr/src/app/config.json ghcr.io/contrast-security-oss/migrate-users-and-groups:main <...args...>
```

#### Local build
```bash
docker build . --tag contrast-migrate-users-groups # Build the container
docker run -it -v $PWD/config.json:/usr/src/app/config.json contrast-migrate-users-groups <...args...> # Run the container
```

### Local use
Use of a virtual environment is encouraged
```bash
python3 -m venv venv # Create the virtual environment
. venv/bin/activate # Activate the virtual environment
pip3 install -r requirements.txt # Install dependencies
python3 contrast_migrate_users_groups.py <args> # Run script
```

## Connection and Authentication

Connection details for your source and destination environments should be specified in the format described in [`config.json.tmpl`](config.json.tmpl).


## Running

You must confirm creation of users and groups.
Output should be as follows:

```
testing connection with instance 'source'
testing connection with instance 'destination'
INFO: Listing users
     Users already in source and dest
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                Username                 ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│      testuser@contrastsecurity.com      │
│   josh.anderson@contrastsecurity.com    │
└─────────────────────────────────────────┘
              Users to create
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                Username                 ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│          jenkins@example.org            │
│          jenkins_api@example.org        │
└─────────────────────────────────────────┘
[?] Okay to create user(s)? (y/N): y

Creating user 'jenkins@example.org'
Creating user 'jenkins_api@example.org'
Creating users... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
INFO: Listing groups and their users
   Groups already in
    source and dest
┏━━━━━━━━━━━━━━━━━━━━━┓
┃        Group        ┃
┡━━━━━━━━━━━━━━━━━━━━━┩
│  ExampleAdminGroup  │
│ JenkinsMultipleOrgs │
└─────────────────────┘
   Groups to create
┏━━━━━━━━━━━━━━━━━━━━━┓
┃        Group        ┃
┡━━━━━━━━━━━━━━━━━━━━━┩
│  ExampleEditGroup   │
└─────────────────────┘
[?] Okay to create group(s)? (y/N): y

Creating group 'ExampleEditGroup' with role 'rules_admin' and member(s):
Creating groups... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
```

## Development Setup
Various tools enforce code standards, and are run as a pre-commit hook. This must be setup before committing changes with the following commands:
```bash
python3 -m venv venv # setup a virtual environment
. venv/bin/activate # activate the virtual environment
pip3 install -r requirements-dev.txt # install development dependencies (will also include app dependencies)
pre-commit install # setup the pre-commit hook which handles formatting
```
