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
    login_request = urllib2.Request("https://connectivity.mach.com/customer/index.php", datagen, headers)
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
    request = urllib2.Request("https://connectivity.mach.com/customer/messagetracking.php", datagen, headers)
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
        # billable information not complete, delete billable item and set MessageLog item to not billed
        message = MessageLog.get(billable.log_id)
        message.billed = False
        message.billing_errors.append("Could not verify Mach billable after several attempts.")
        message.save()
        billable.delete()

def format_start_end_suffixes(start=None, end=None):
    if isinstance(start, datetime.datetime):
        start = start.isoformat()
    if isinstance(end, datetime.datetime):
        end = end.isoformat()
    startkey_suffix = [start] if start else []
    endkey_suffix = [end] if end else [{}]
    return startkey_suffix, endkey_suffix