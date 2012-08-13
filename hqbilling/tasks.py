import datetime
import logging
import re
from celery.schedules import crontab, schedule
from celery.decorators import periodic_task, task
from django.conf import settings
import urllib2
from hqbilling.models import MachSMSRate, UnicelSMSRate, TropoSMSRate, MachSMSBillable, \
    MachPhoneNumber, HQMonthlyBill, BillableCurrency
from hqbilling.utils import get_mach_data, deal_with_delinquent_mach_billable

class first_of_month(schedule):
    # from http://stackoverflow.com/questions/4397530/how-do-i-schedule-a-task-with-celery-that-runs-on-1st-of-every-month
    def is_due(self, last_run_at):
        now = datetime.datetime.now()
        if now.month > last_run_at.month and now.day == 1:
            return True, 3600
        return False, 3600

    def __repr__(self):
        return "<first of month>"

@periodic_task(run_every=crontab(minute=0, hour='*/6'))
def update_currency_conversion():
    rate_classes = [MachSMSRate, TropoSMSRate, UnicelSMSRate]
    rate_codes = [klass.currency_code_setting() for klass in rate_classes]
    currencies = BillableCurrency.view("hqbilling/active_currency",
        group=True
    ).all()
    relevant_codes = [cur.get('key')[0] for cur in currencies]
    relevant_codes.extend(rate_codes)
    relevant_codes = list(set(relevant_codes))
    for code in relevant_codes:
        currency = BillableCurrency.get_existing_or_new_by_code(code)
        currency.update_conversion_rate()
        currency.save()

@task
def bill_client_for_sms(klass, message_id, **kwargs):
    from corehq.apps.sms.models import MessageLog
    try:
        message = MessageLog.get(message_id)
    except Exception as e:
        logging.error("Failed to retrieve message log corresponding to billable: %s" % e)
        return
    try:
        klass.handle_api_response(message, **kwargs)
    except Exception as e:
        logging.error("Failed create billable item from message %s.\n ERROR: %s" % (message, e))

@periodic_task(run_every=crontab(minute=0, hour=0))
def update_mach_billables():
    mach_data = get_mach_data(days=3)
    try:
        rateless_billables = MachSMSBillable.get_rateless().all()
        for billable in rateless_billables:
            billable.sync_attempts.append(datetime.datetime.utcnow())
            for data in mach_data:
                phone_number = data[3]
                if phone_number == billable.phone_number:
                    mach_number = MachPhoneNumber.get_by_number(phone_number, data)
                    rate_item = MachSMSRate.get_by_number(billable.direction, mach_number)
                    if rate_item:
                        billable.update_item_from_form(rate_item)
                        billable.save()
                    billable.update_mach_delivery_status(data)
                    billable.save()
                    if billable.rate_id and billable.mach_delivered_date:
                        break
            deal_with_delinquent_mach_billable(billable)

        statusless_billables = MachSMSBillable.get_statusless().all()
        for billable in statusless_billables:
            billable.sync_attempts.append(datetime.datetime.utcnow())
            for data in mach_data:
                billable.update_mach_delivery_status(data)
                billable.save()
                if billable.mach_delivered_date:
                    break
            deal_with_delinquent_mach_billable(billable)

    except Exception as e:
        logging.error("There was an error updating mach billables: %s" % e)


@periodic_task(run_every=first_of_month())
def generate_monthly_bills():
    from corehq.apps.domain.models import Domain
    for domain in Domain.get_all():
        HQMonthlyBill.create_bill_for_domain(domain)
