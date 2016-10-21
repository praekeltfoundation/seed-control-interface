from seed_control_interface.celery import app


@app.task
def email_report(recipients, start_date, end_date):
    from django.core.management import call_command
