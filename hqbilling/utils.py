import logging
import cookielib
import re
import datetime
from django.conf import settings
import poster
import urllib2
from corehq.apps.sms.models import MessageLog

def get_mach_data(days=1):
    if days not in [1,3,7,14]:
        logging.error("Not formatted properly.")
        return []
    mach_login = dict(
        user=settings.MACH_CONFIG.get("username",""),
        password=settings.MACH_CONFIG.get("password",""),
        mode="login",
        mc="",
        m=""
    )
    opener = poster.streaminghttp.register_openers()
    cj = cookielib.CookieJar()
    opener.add_handler(urllib2.HTTPCookieProcessor(cj))
    datagen, headers = poster.encode.multipart_encode(mach_login)
    login_request = urllib2.Request("https://a2p.syniverse.com/customer/index.php", datagen, headers)
    urllib2.urlopen(login_request) #login and grab the cookies
    mach_post = dict(
        dnr="",
        snr="",
        userkey="",
        simpledate=days,
        date_begin="",
        date_end="",
        countryid="All",
        netid="All",
        statusfilter="All",
        errorfilter="Alle",
        number=10,
        csvdownload="on"
    )
    datagen, headers = poster.encode.multipart_encode(mach_post)
    request = urllib2.Request("https://a2p.syniverse.com/customer/messagetracking.php", datagen, headers)
    resp = urllib2.urlopen(request)
    data = resp.read()
    mach_data = re.split(',|\n',data)
    mach_data = mach_data[mach_data.index('MsgID'):]
    mach_data = mach_data[mach_data.index('')+1:]
    mach_data = mach_data[:-mach_data[::-1].index('')-1]
    if len(mach_data) % 8 > 0:
        logging.error("Data Returned from Mach not formatted as expected. Ignoring as a precaution.")
        return []
    else:
        # grab the latest phone # to carrier match
        mach_data = [mach_data[i:i+8] for i in range(0, len(mach_data), 8)]
        return mach_data

def deal_with_delinquent_mach_billable(billable):
    if len(billable.sync_attempts) > 6 and not (billable.rate_id and billable.mach_delivered_date):
        # billable information not complete, mark billable item as error and do not charge for the message.
        message = MessageLog.get(billable.log_id)
        message.billed = False
        message.billing_errors.append("Could not verify Mach billable after several attempts.")
        message.save()

        now = datetime.datetime.utcnow()
        # officially close out the billable
        billable.billable_date = billable.billable_date or now
        billable.modified_date = billable.modified_date or now
        billable.mach_delivered_date = billable.mach_delivered_date or now
        from hqbilling.models import UNKNOWN_RATE_ID
        billable.rate_id = billable.rate_id or UNKNOWN_RATE_ID
        if billable.mach_delivery_status != "accepted":
            # generally the status will say something other than accepted after a while once it's actually accepted,
            # however, sometimes it just stays at this. If it has any other delivery status at this point, mark it as
            # an error.
            billable.billable_amount = 0
            billable.conversion_rate = 1
            billable.dimagi_surcharge = billable.dimagi_surcharge or 0
            billable.has_error = True
            if not billable.error_message:
                billable.error_message = "Mach failed to send message due to '%s'" % billable.mach_delivery_status

        billable.save()

def format_start_end_suffixes(start=None, end=None):
    if isinstance(start, datetime.datetime):
        start = start.isoformat()
    if isinstance(end, datetime.datetime):
        end = end.isoformat()
    startkey_suffix = [start] if start else []
    endkey_suffix = [end] if end else [{}]
    return startkey_suffix, endkey_suffix
