FROM python:3.10-alpine@sha256:b974a5de91b4ac6da8313502cd5bfe65c499e390d32658e1f2deea26fa5afb14

WORKDIR /usr/src/app
RUN mkdir output

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./

ENTRYPOINT [ "python", "contrast_migrate_users_groups.py" ]
