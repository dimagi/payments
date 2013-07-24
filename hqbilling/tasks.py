import datetime
from celery.schedules import crontab, schedule
from celery.task import periodic_task, task
from celery.utils.log import get_task_logger
from django.conf import settings
from hqbilling.models import MachSMSRate, UnicelSMSRate, TropoSMSRate, MachSMSBillable, \
    MachPhoneNumber, HQMonthlyBill, BillableCurrency
from hqbilling.utils import get_mach_data, deal_with_delinquent_mach_billable

logging = get_task_logger(__name__)

class first_of_month(schedule):
    """
    Wake up, wake up, wake up it's the...
    """
    # from http://stackoverflow.com/questions/4397530/how-do-i-schedule-a-task-with-celery-that-runs-on-1st-of-every-month
    def is_due(self, last_run_at):
        now = datetime.datetime.now()
        if now.month > last_run_at.month and now.day == 1:
            return True, 3600
        return False, 3600

    def __repr__(self):
        return "<first of month>"

@periodic_task(run_every=crontab(minute=0, hour='*/6'), queue=getattr(settings, 'CELERY_PERIODIC_QUEUE','celery'))
def update_currency_conversion():
    rate_classes = [MachSMSRate, TropoSMSRate, UnicelSMSRate]
    rate_codes = [klass._admin_crud_class.currency_code for klass in rate_classes]
    currencies = BillableCurrency.view(BillableCurrency._currency_view,
        group=True
    ).all()
    relevant_codes = [cur.get('key')[0] for cur in currencies]
    relevant_codes.extend(rate_codes)
    relevant_codes = list(set(relevant_codes))
    for code in relevant_codes:
        currency = BillableCurrency.get_existing_or_new_by_code(code)
        currency.set_live_conversion_rate(currency.currency_code, settings.DEFAULT_CURRENCY.upper())
        currency.save()

@task
def bill_client_for_sms(klass, message_id, **kwargs):
    from corehq.apps.sms.models import MessageLog
    try:
        message = MessageLog.get(message_id)
    except Exception as e:
        logging.exception("Failed to retrieve message log corresponding to billable: %s" % e)
        return
    try:
        klass.handle_api_response(message, **kwargs)
    except Exception as e:
        logging.exception("Failed create billable item from message %s.\n ERROR: %s" % (message, e))

@periodic_task(run_every=crontab(minute=0, hour='*/12'), queue=getattr(settings, 'CELERY_PERIODIC_QUEUE','celery'))
def update_mach_billables():
    mach_data = get_mach_data(days=3)
    try:
        # rateless billables are Mach Billables that do not have a delivered date
        rateless_billables = MachSMSBillable.get_rateless().all()
        for billable in rateless_billables:
            billable.sync_attempts.append(datetime.datetime.utcnow())
            for data in mach_data:
                phone_number = data[3]
                if phone_number == billable.phone_number:
                    mach_number = MachPhoneNumber.get_by_number(phone_number, data)
                    rate_item = MachSMSRate.get_by_number(billable.direction, mach_number)

                    billable.calculate_rate(rate_item)
                    billable.save()

                    billable.update_mach_delivery_status(data)
                    billable.save()

                    if billable.rate_id and billable.mach_delivered_date:
                        break
            deal_with_delinquent_mach_billable(billable)

        # statusless billables are Mach Billables that were not confirmed as deivered
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


@periodic_task(run_every=first_of_month(), queue=getattr(settings, 'CELERY_PERIODIC_QUEUE','celery'))
def generate_monthly_bills(billing_range=None, domain_name=None):
    logging.info("[Billing] Generating Monthly Bills")
    from corehq.apps.domain.models import Domain
    domains = [Domain.get_by_name(domain_name)] if domain_name is not None else Domain.get_all()
    for domain in domains:
        HQMonthlyBill.create_bill_for_domain(domain.name, billing_range=billing_range)
