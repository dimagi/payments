import datetime
from celery.schedules import crontab
from celery.decorators import periodic_task, task
from hqpayments.models import *
from django.conf import settings
from hqpayments.utils import get_mach_data, deal_with_delinquent_mach_billable

#@periodic_task(run_every=crontab(minute=0, hour='*/6'))
@periodic_task(run_every=crontab())
def update_currency_rate():
    relevant_classes = [MachSMSBillableRate(), TropoSMSBillableRate(), UnicelSMSBillableRate()]
    for klass in relevant_classes:
        currency_code = klass.currency_code_setting
        rate = CurrencyConversionRate.get_by_code(currency_code)
        if currency_code.upper() == settings.DEFAULT_CURRENCY.upper():
            rate.conversion = 1.0
            rate.source = "default"
        else:
            url = "http://www.google.com/ig/calculator?hl=en&q=1%s=?%s" % (currency_code, settings.DEFAULT_CURRENCY)
            try:
                data = urllib2.urlopen(url).read()
                # AGH GOOGLE WHY DON'T YOU RETURN VALID JSON??? ?#%!%!%@#
                rhs = re.compile('rhs:\s*"([^"]+)"')
                data = rhs.search(data).group()
                cur = re.compile('[0-9.]+')
                data = cur.search(data).group()
                rate.conversion = float(data)
                print rate.conversion
            except Exception as e:
                rate.conversion = 0.0
                url = "ERROR: %s, %s" % (e, url)
            rate.source = url
        rate.last_updated = datetime.datetime.utcnow()
        rate.save()

@task
def bill_client_for_sms(klass, message, **kwargs):
    try:
        klass = eval(klass)
    except Exception:
        logging.error("Failed to parse Billable Item class. %s" % klass)
        return
    try:
        klass.create_from_message(message, **kwargs)
    except Exception as e:
        logging.error("Failed create billable item from message %s.\n ERROR: %s" % (message, e))

@periodic_task(run_every=crontab(minute=0, hour=0))
def update_mach_billables():
    mach_data = get_mach_data(days=3)
    try:
        rateless_billables = MachSMSBillableItem.get_rateless().all()
        for billable in rateless_billables:
            billable.sync_attempts.append(datetime.datetime.utcnow())
            for data in mach_data:
                phone_number = data[3]
                if phone_number == billable.phone_number:
                    mach_number = MachPhoneNumber.get_by_number(phone_number, data)
                    rate_item = MachSMSBillableRate.get_by_number(billable.direction, mach_number)
                    if rate_item:
                        billable.update_rate(rate_item)
                        billable.save()
                    billable.update_mach_delivery_status(data)
                    billable.save()
                    if billable.rate_id and billable.mach_delivered_date:
                        break
            deal_with_delinquent_mach_billable(billable)

        statusless_billables = MachSMSBillableItem.get_statusless().all()
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



