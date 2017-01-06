======================
Seed Control Interface
======================

Control Interface for Seed Services.

Uses seed-auth-api for Authentication and permissions
Uses seed-control-interface-service for configuration of services

Connects to:
* seed-identity-store
# seed-control-interface


Local installation
------------------

    $ git clone git@github.com:praekelt/seed-control-interface.git
    $ cd seed-control-interface
    $ virtualenv ve
    $ source ve/bin/activate
    $ pip install -e .


How to generate a report
------------------------

Currently there's a single management command to run after cloning this
repository and installing all the dependencies:

    $ python manage.py generate_reports \
        --hub-url=https://registration.mama.ng.p16n.org/api/v1/ \
        --hub-token=<INSERT YOUR HUB/REGISTRATION TOKEN HERE> \
        --identity-store-url=https://identity-store.mama.ng.p16n.org/api/v1/ \
        --identity-store-token=<INSERT YOUR IDENTITY STORE TOKEN HERE> \
        --output-file=generated-file-name.xlsx \
        --start=2016-10-10 \
        --end=2016-10-17

This will run for a minute or two and when done will have generated the
"generated-file-name.xlsx" XLS file in the current directory.
