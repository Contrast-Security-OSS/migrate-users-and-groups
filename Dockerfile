FROM python:3.11.0-alpine

WORKDIR /usr/src/app
RUN mkdir output

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./

ENTRYPOINT [ "python", "contrast_migrate_users_groups.py" ]
