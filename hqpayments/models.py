# Stub models file
import logging
import re
import urllib
from couchdbkit.ext.django.schema import *
import datetime
import decimal
import dateutil
from django.conf import settings
import urllib2
import phonenumbers
import pytz
from dimagi.utils.timezones import utils as tz_utils
from hqpayments.utils import get_mach_data

DEFAULT_BASE = 1
INCOMING = "I"
OUTGOING = "O"
SMS_DIRECTIONS = {
    INCOMING: "Incoming",
    OUTGOING: "Outgoing"
}
MACH_NL_URL = "http://nls1.mach.com/ws/http?id=%(username)s&pw=%(password)s&sp=%(service_profile)s&msisdn=%(phone_number)s"


class SMSBillableItem(Document):
    billable_date = DateTimeProperty()
    billable_amount = DecimalProperty()
    conversion_rate = DecimalProperty() # conversion rate at the time of creating the billable item
    rate_id = StringProperty()
    log_id = StringProperty()

    # Summary Info
    domain = StringProperty()
    direction = StringProperty()
    phone_number = StringProperty()

    @classmethod
    def couch_view(cls):
        return "hqpayments/all_billable_items"

    @classmethod
    def get_all(cls, include_docs=True):
        return cls.view(cls.couch_view(),
            reduce=False,
            include_docs = include_docs
        )

    @classmethod
    def by_domain(cls, domain, include_docs=True):
        key =["domain", domain]
        return cls.view(cls.couch_view(),
            reduce=False,
            include_docs = include_docs,
            startkey = key,
            endkey = key+[{}])

    @classmethod
    def by_domain_and_direction(cls, domain, direction, include_docs=True):
        key =["domain direction", domain, direction]
        return cls.view(cls.couch_view(),
            reduce=False,
            include_docs = include_docs,
            startkey = key,
            endkey = key+[{}])

    @classmethod
    def create_from_message(cls, message, **kwargs):
        if message.billing_errors:
            logging.error("ERRORS billing SMS Message with ID %s:\n%s" % (message._id, "\n".join(message.billing_errors)))
            message.save()

    @classmethod
    def save_from_message(cls, rate_item, message):
        billable = None
        if rate_item:
            billable = cls()
            billable.update_rate(rate_item)
            billable.update_message(message)
            billable.save()
        else:
            message.billing_errors.append("Billing rate entry could not be found.")
        return dict(billable=billable, message=message)

    def update_rate(self, rate_item):
        if rate_item:
            self.billable_date = datetime.datetime.utcnow()
            self.billable_amount = rate_item.billable_amount
            self.conversion_rate = rate_item.conversion_rate
            self.rate_id = rate_item._id

    def update_message(self, message):
        self.log_id = message._id
        self.domain = message.domain
        self.direction = message.direction
        self.phone_number = message.phone_number
        message.billed = True
        message.save()

class UnicelSMSBillableItem(SMSBillableItem):
    unicel_id = StringProperty()

    @classmethod
    def couch_view(cls):
        return "hqpayments/unicel_billable_items"

    @classmethod
    def create_from_message(cls, message, **kwargs):
        response = kwargs.get('response', None)
        match_key = UnicelSMSBillableRate.generate_match_key(**dict(direction=message.direction))
        rate_item = UnicelSMSBillableRate.get_by_match(match_key)
        if not rate_item:
            message.billing_errors.append("No Unicel rate item could be found for key: %s" % match_key)
        elif isinstance(response, str) and len(response) > 0:
            # attempt to figure out if there was an error in sending the message.
            # Look for something like '0x200 - ' in the returned string
            # A successful return will just be a uuid from Unicel.
            find_err = re.compile('\dx\d\d\d\s-\s')
            match = find_err.search(response)
            if not match:
                result = cls.save_from_message(rate_item, message)
                billable = result.get('billable', None)
                if billable:
                    billable.unicel_id = response
                    billable.save()
                    return
                else:
                    message.billing_errors.extend(result.get('message', []))
            else:
                message.billing_errors.append("Attempted to send message via UNICEL api and received errors. Client not billed. Errors: %s" % response)
        elif message.direction == INCOMING:
            result = cls.save_from_message(rate_item, message)
            billable = result.get('billable', None)
            if billable:
                billable.unicel_id = "incoming"
                billable.save()
                return
        else:
            message.billing_errors.append("Attempt to send message via UNICEL api resulted in an error.")
        super(UnicelSMSBillableItem, cls).create_from_message(message, **kwargs)


class TropoSMSBillableItem(SMSBillableItem):
    tropo_id = StringProperty()

    @classmethod
    def couch_view(cls):
        return "hqpayments/tropo_billable_items"

    @classmethod
    def create_from_message(cls, message, **kwargs):
        response = kwargs.get("response")
        find_success = re.compile('(<success>).*(</success>)')
        match = find_success.search(response)
        successful = bool(match and match.group() == '<success>true</success>')
        if successful:
            logging.info("Tropo Success")
            rate_item = TropoSMSBillableRate.get_by_match(
                TropoSMSBillableRate.generate_match_key(**dict(direction=message.direction,
                    domain=message.domain
                )))
            result = cls.save_from_message(rate_item, message)
            billable = result.get('billable', None)
            if billable:
                billable.tropo_id = cls.get_tropo_id(response)
                billable.save()
        else:
            message.billing_errors.append("An error occurred while sending a message through the Tropo API.")
        super(TropoSMSBillableItem, cls).create_from_message(message, **kwargs)

    @classmethod
    def get_tropo_id(cls, response):
        id_reg = re.compile('(<id>[a-zA-Z0-9][a-zA-Z0-9][a-zA-Z0-9]+)')
        match = id_reg.search(response)
        if match and len(match.group()) > 4:
            return match.group()[4:]
        return None


class MachSMSBillableItem(SMSBillableItem):
    contacted_mach_api = DateTimeProperty()
    sync_attempts = ListProperty()
    mach_delivery_status = StringProperty()
    mach_id = StringProperty()
    mach_delivered_date = DateTimeProperty()

    def update_message(self, message):
        self.sync_attempts.append(datetime.datetime.utcnow())
        super(MachSMSBillableItem, self).update_message(message)

    def update_mach_delivery_status(self, api_info):
        delivered_on = api_info[-3]
        delivery_status = api_info[-1]
        mach_id = api_info[0]
        if delivered_on:
            delivered_on = delivered_on.replace(". ", ".%s " % datetime.datetime.now().year)
            try:
                delivered_on = datetime.datetime.strptime(delivered_on, "%d.%m.%Y %H:%M:%S")
                berlin = pytz.timezone('Europe/Berlin')
                is_dst = tz_utils.is_timezone_in_dst(berlin, delivered_on)
                delivered_on = berlin.localize(delivered_on, is_dst=is_dst).astimezone(pytz.utc)
                contact = datetime.datetime.replace(self.contacted_mach_api, tzinfo=pytz.utc)
                td = contact-delivered_on
                total_seconds = abs(td.seconds + td.days * 24 * 3600)
                existing = self.get_by_mach_id(mach_id).first()
                # allowing three minutes of latency and making sure that the mach_id is unique
                if total_seconds <= 60*3 and not existing:
                    self.mach_id = mach_id
                    self.mach_delivery_status = delivery_status
                    self.mach_delivered_date = delivered_on
            except Exception as e:
                logging.info("Error parsing mach API delivery info: %s" % e)
        elif delivery_status == 'accepted':
            # message has not been delivered yet
            self.mach_id = mach_id
            self.mach_delivery_status = delivery_status

    @classmethod
    def couch_view(cls):
        return "hqpayments/mach_billable_items"

    @classmethod
    def get_by_mach_id(cls, mach_id, include_docs=True):
        return cls.view("hqpayments/mach_billable_items_by_mach_id",
            reduce=False,
            include_docs=include_docs,
            startkey=[mach_id],
            endkey=[mach_id, {}]
        )

    @classmethod
    def get_rateless(cls, include_docs=True):
        return cls.view('hqpayments/mach_billable_rateless',
            reduce=False,
            include_docs=include_docs
        )

    @classmethod
    def get_statusless(cls, include_docs=True):
        return cls.view('hqpayments/mach_billable_statusless',
            reduce=False,
            include_docs=include_docs
        )

    @classmethod
    def create_from_message(cls, message, **kwargs):
        response = kwargs.get('response', None)
        if isinstance(response, str) or isinstance(response, unicode):
            api_success = bool("+OK" in response)
            if api_success:
                mach_data = get_mach_data()
                if mach_data:
                    last_message = mach_data[0]
                    phone_number = last_message[3]
                    billable = cls()
                    billable.update_message(message)
                    billable.contacted_mach_api = datetime.datetime.now(tz=pytz.utc)
                    if phone_number == message.phone_number:
                        # same phone number, now check delivery date
                        billable.update_mach_delivery_status(last_message)
                    mach_number = MachPhoneNumber.get_by_number(message.phone_number, last_message)
                    if mach_number:
                        rate_item = MachSMSBillableRate.get_by_number(message.direction, mach_number).first()
                        if rate_item:
                            billable.update_rate(rate_item)
                    billable.save()
                else:
                    message.billing_errors.append("There was an error retrieving message delivery information from Mach.")
            else:
                message.billing_errors.append("There was an error accessing the MACHI API.")
        else:
            message.billing_errors.append("There was an error while trying to send an SMS to via Mach.")
        super(MachSMSBillableItem, cls).create_from_message(message, **kwargs)


class CurrencyConversionRate(Document):
    last_updated = DateTimeProperty()
    conversion = DecimalProperty()
    source = StringProperty()

    @classmethod
    def get_by_code(cls, currency_code):
        currency_id = "CURRENCY_CONVERSION_RATE_%s" % (currency_code.upper().strip())
        try:
            conversion_rate = cls.get(currency_id)
        except Exception:
            conversion_rate = None
        if not conversion_rate:
            conversion_rate = cls(dict(_id=currency_id))
            conversion_rate.save()
        return conversion_rate


class SMSBillableRate(Document):
    direction = StringProperty()
    last_modified = DateTimeProperty()
    currency_code = StringProperty(default=settings.DEFAULT_CURRENCY)
    base_fee = DecimalProperty()
    surcharge = DecimalProperty(default=0)

    @classmethod
    def match_view(cls):
        return ""

    @property
    def currency_code_setting(self):
        return settings.DEFAULT_CURRENCY

    @property
    def currency_character(self):
        return "$"

    @property
    def column_list(self):
        return ["direction", "base_fee", "surcharge"]

    @property
    def default_base_fee(self):
        return DEFAULT_BASE

    @property
    def default_surcharge(self):
        return 0

    @property
    def as_row(self):
        keys = self.column_list
        ROUNDPLACES = decimal.Decimal(10) ** -3
        row = []
        for key in keys:
            property = getattr(self, key)
            if isinstance(property, decimal.Decimal):
                property = property.quantize(ROUNDPLACES)
                row.append("%s %s" % (self.currency_character, property))
            elif key == "direction":
                row.append(SMS_DIRECTIONS[property])
            else:
                row.append(property)
        row.append('<a href="#updateRateModal" class="btn" onclick="rateUpdateManager.updateRate(this)" data-rateid="%s" data-toggle="modal">Edit</a>' % self._id)
        return row

    @property
    def billable_amount(self):
        return self.base_fee + self.surcharge

    @property
    def conversion_rate(self):
        rate = 0.0
        try:
            r = CurrencyConversionRate.get_by_code(self.currency_code)
            rate = r.conversion
        except Exception as e:
            logging.error("Could not get conversion rate. Error: %s" % e)
        return decimal.Decimal(rate)

    def update_rate(self, overwrite=True, **kwargs):
        self.direction = kwargs.get('direction', OUTGOING)
        if overwrite:
            self.currency_code = self.currency_code_setting
            self.last_modified = datetime.datetime.utcnow()
            self.base_fee = self.correctly_format_rate(kwargs.get('base_fee', self.default_base_fee))
            self.surcharge = self.correctly_format_rate(kwargs.get('surcharge', self.default_surcharge))
        self.save()

    @classmethod
    def get_by_match(cls, match_key):
        rate = cls.view(cls.match_view(),
            reduce=False,
            include_docs=True,
            startkey=match_key,
            endkey=match_key+[{}],
        ).first()
        return rate

    @classmethod
    def update_rate_by_match(cls, overwrite=True, **kwargs):
        rate = cls.get_by_match(cls.generate_match_key(**kwargs))
        if not rate:
            rate = cls()
            overwrite = True
        rate.update_rate(overwrite, **kwargs)
        return rate

    @staticmethod
    def generate_match_key(**kwargs):
        return [str(kwargs.get('direction', 'I'))]

    @staticmethod
    def correctly_format_rate(rate):
        if isinstance(rate, str):
            rate = "%f" % rate
        return rate

class MachSMSBillableRate(SMSBillableRate):
    country_code = StringProperty()
    country = StringProperty()
    iso = StringProperty()
    mcc = StringProperty()
    mnc = StringProperty()
    network = StringProperty()

    @classmethod
    def match_view(cls):
        return "hqpayments/mach_rates"

    @property
    def currency_code_setting(self):
        return "EUR"

    @property
    def currency_character(self):
        return "&euro;"

    @property
    def column_list(self):
        return ["country_code",
                "iso",
                "country",
                "mcc",
                "mnc",
                "network",
                "base_fee",
                "surcharge",
                "direction"]

    @staticmethod
    def correctly_format_codes(code):
        if isinstance(code, float) or isinstance(code, int):
            code = "%d" % code
        return code

    @classmethod
    def update_rate_by_match(cls, overwrite=True, **kwargs):
        kwargs['country_code'] = cls.correctly_format_codes(kwargs.get('country_code', ''))
        kwargs['mcc'] = cls.correctly_format_codes(kwargs.get('mcc', ''))
        kwargs['mnc'] = cls.correctly_format_codes(kwargs.get('mnc', ''))
        return super(MachSMSBillableRate, cls).update_rate_by_match(overwrite, **kwargs)

    def update_rate(self, overwrite=True, **kwargs):
        self.mcc = kwargs.get('mcc')
        self.mnc = kwargs.get('mnc')
        self.country_code = kwargs.get('country_code')
        if overwrite:
            self.country = kwargs.get('country', '')
            self.network = kwargs.get('network', '')
            self.iso = str(kwargs.get('iso', ''))
        super(MachSMSBillableRate, self).update_rate(overwrite, **kwargs)

    @staticmethod
    def generate_match_key(**kwargs):
        return [kwargs.get('direction', 'I'),
                kwargs.get('country_code', ''),
                kwargs.get('mcc', ''),
                kwargs.get('mnc', '')]

    @classmethod
    def get_by_network(cls, direction, country, network, include_docs=True):
        key = [direction, country, network]
        return cls.view("hqpayments/mach_rates_by_network",
            reduce=False,
            include_docs=include_docs,
            startkey=key,
            endkey=key+[{}]
        )

    @classmethod
    def get_by_number(cls, direction, mach_number, include_docs=True):
        return cls.get_by_network(direction, mach_number.country, mach_number.network, include_docs)


class TropoSMSBillableRate(SMSBillableRate):
    domain = StringProperty()

    @classmethod
    def match_view(cls):
        return "hqpayments/tropo_rates"

    @property
    def column_list(self):
        return ["domain",
                "direction",
                "base_fee",
                "surcharge"]

    @staticmethod
    def generate_match_key(**kwargs):
        return [kwargs.get('direction', 'I'),
                kwargs.get('domain', '')]

    def update_rate(self, overwrite=True, **kwargs):
        self.domain = kwargs.get('domain')
        super(TropoSMSBillableRate, self).update_rate(overwrite, **kwargs)


class UnicelSMSBillableRate(SMSBillableRate):
    @classmethod
    def match_view(cls):
        return "hqpayments/unicel_rates"



class MachPhoneNumber(Document):
    phone_number = StringProperty()
    network = StringProperty()
    country = StringProperty()

    @classmethod
    def get_by_number(cls, number, api_info):
        try:
            [country, network] = api_info[-2].strip().split('  ')
        except Exception:
            country = None
            network = None
        try:
            mach_number = cls.view("hqpayments/mach_phone_numbers",
                reduce=False,
                include_docs=True,
                startkey=[number],
                endkey=[number,{}]
            ).first()
            if not mach_number:
                mach_number = cls()
            if country and network:
                mach_number.country = country
                mach_number.network = network
                mach_number.save()
            return mach_number
        except Exception as e:
            logging.error("Error retrieving mach phone number: %s" % e)
            return None

