import datetime
from celery.schedules import crontab
from celery.decorators import periodic_task, task
import urllib2
import json
import re
from corehq.apps.reports.models import DailyReportNotification
from corehq.apps.sms.models import MessageLog
from hqpayments.models import *
from django.conf import settings

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
def bill_client_for_sms(klass, message_id, **kwargs):
    logging.error(kwargs)
    try:
        message = MessageLog.get(message_id)
    except Exception as e:
        logging.error("could not create message log item from message id %s. \n ERROR: %s" % (message_id, e))
        return

    try:
        klass = eval(klass)
    except Exception:
        logging.error("Failed to parse Billable Item class. %s" % klass)
        return

    try:
        klass.create_from_message(message, **kwargs)
    except Exception as e:
        logging.error("Failed create billable item from message %s.\n ERROR: %s" % (message, e))