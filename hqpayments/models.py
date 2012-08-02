# Stub models file
import logging
import re
import urllib
from couchdbkit.ext.django.schema import *
import datetime
import decimal
from django.conf import settings
import urllib2
import phonenumbers

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
    log_id = StringProperty()
    rate_id = StringProperty()

    @classmethod
    def create_from_message(cls, message, **kwargs):
        if message.billing_errors:
            logging.error("ERRORS billing SMS Message with ID %s:\n%s" % (message._id, "\n".join(message.billing_errors)))
            message.save()

    @classmethod
    def save_from_message(cls, rate_item, message, **kwargs):
        billable = None
        if rate_item:
            billable = cls()
            billable.billable_date = datetime.datetime.utcnow()
            billable.billable_amount = rate_item.billable_amount
            billable.conversion_rate = rate_item.conversion_rate
            billable.log_id = message._id
            billable.rate_id = rate_item._id
            billable.save()
            message.billed = True
            message.save()
        else:
            message.billing_errors.append("Could not bill successfully sent UNICEL message, as billing rate entry could not be found.")
        return dict(billable=billable, message=message)


class UnicelSMSBillableItem(SMSBillableItem):
    message_id_from_api = StringProperty()

    @classmethod
    def create_from_message(cls, message, **kwargs):
        response = kwargs.get('response', None)
        rate_item = UnicelSMSBillableRate.get_by_match(
            UnicelSMSBillableRate.generate_match_key(**dict(direction=message.direction))
        )
        if isinstance(response, str) and len(response) > 0:
            # attempt to figure out if there was an error in sending the message. Look for \dx\d\d\d in the returned string
            find_err = re.compile('\dx\d\d\d\s-\s')
            match = find_err.search(response)
            if not match:
                result = cls.save_from_message(rate_item, message)
                billable = result.get('billable', None)
                if billable:
                    billable.message_id_from_api = response
                    billable.save()
                    return
                else:
                    message.billing_errors.extend(result.get('message', []))
            else:
                message.billing_errors.append("Attempted to send message via UNICEL api and received errors. Client not billed. Errors: %s" % response)
        elif message.direction == INCOMING:
            result = cls.save_from_message(UnicelSMSBillableRate, message)
            billable = result.get('billable', None)
            if billable:
                billable.message_id_from_api = "incoming"
                billable.save()
                return
        message.billing_errors.append("Attempt to send message via UNICEL api resulted in an error.")



class TropoSMSBillableItem(SMSBillableItem):

    @classmethod
    def create_from_message(cls, message, **kwargs):
        rate_item = UnicelSMSBillableRate.get_by_match(
            UnicelSMSBillableRate.generate_match_key(**dict(direction=message.direction,
                domain=message.domain
            )))
        # TODO look at the response from the API and decide if billing is necessary
        cls.save_from_message(rate_item, message)
        super(TropoSMSBillableItem, cls).create_from_message(message, **kwargs)

class MachSMSBillableItem(SMSBillableItem):

    @classmethod
    def create_from_message(cls, message, **kwargs):
        response = kwargs.get('response', None)
        if isinstance(response, str):
            print response
            print "PHONE NUBMER, MACH:", message.phone_number

            parts = phonenumbers.parse(message.phone_number, None)
#            number_lookup_url = MACH_NL_URL % dict(
#                username=settings.MACH_CONFIG.get('username',''),
#                password=settings.MACH_CONFIG.get('password',''),
#                service_profile=settings.MACH_CONFIG.get('service_profile', ''),
#                phone_number=urllib.quote(message.phone_number)
#            )



#            print "LOOKING UP NUMBER", number_lookup_url
#            lookup = urllib2.urlopen(number_lookup_url).read()
#            print "LOOKUP RESPONSE", lookup
#            lookup = lookup.split('|')
#            if lookup:
#                if lookup[0] == "0":
#                    country_code = lookup[9]
#                    mcc = lookup[7]
#                    mnc = lookup[8]
#                    key = [message.direction, country_code, mcc, mnc]
#                    rate_item = UnicelSMSBillableRate.view("hqpayments/mach_rates_unique",
#                        startkey=key,
#                        endkey=key+[{}],
#                        reduce=False,
#                        include_docs=True
#                    ).first()
#                    result = cls.save_from_message(rate_item, message)
#                    if result.get('billable', None):
#                        return
#                    else:
#                        message.billable_errors.extend(result.get('message', []))
#                else:
#                    message.billable_errors.append("The number lookup using Mach's API was not successful, so the client wasn't billed")
#            else:
#                message.billing_errors.append("There was an error looking up the number from Mach's api.")
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
    currency_code = StringProperty(settings.DEFAULT_CURRENCY)
    base_fee = DecimalProperty()
    surcharge = DecimalProperty(default=0)

    @classmethod
    def match_view(cls):
        return "hqpayments/unicel_rates"

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

    def billable_amount(self):
        return self.base_fee + self.surcharge

    @property
    def conversion_rate(self):
        rate = 0.0
        try:
            r = CurrencyConversionRate.get_by_code(self.currency_code)
            rate = r.conversion
        except Exception:
            pass
        return rate

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
        return [kwargs.get('direction', 'I')]

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





