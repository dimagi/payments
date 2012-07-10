# Stub models file
from couchdbkit.ext.django.schema import *
import datetime
import decimal

MACH_DEFAULT_BASE = 1
INCOMING = "I"
OUTGOING = "O"

class SMSBillableItem(Document):
    billable_date = DateTimeProperty()
    billable_amount = DecimalProperty()
    conversion_rate = DecimalProperty()
    log_id = StringProperty()
    billable_rate_id = StringProperty()

class SMSBillableRate(Document):
    direction = StringProperty()
    last_modified = DateTimeProperty()
    currency_code = StringProperty("USD")
    base_fee = DecimalProperty()
    surcharge = DecimalProperty()

    def calculate_billable_rate(self):
        pass

    def get_conversion_rate(self):
        pass

class MachSMSBillableRate(SMSBillableRate):
    country_code = StringProperty()
    country = StringProperty()
    iso = StringProperty()
    mcc = StringProperty()
    mnc = StringProperty()
    network = StringProperty()

    @property
    def as_tr(self):
        keys = ["country_code",
            "iso",
            "country",
            "mcc",
            "mnc",
            "network",
            "base_fee",
            "surcharge"]
        TWOPLACES = decimal.Decimal(10) ** -2
        row = ["<tr>"]

        for key in keys:
            property = getattr(self, key)
            print type(property)
            if isinstance(property, decimal.Decimal):
                property = property.quantize(TWOPLACES)
                row.append("<td>&euro;%s</td>" % property)
            else:
                row.append("<td>%s</td>" % property)
        row.append("<td>Edit</td>")
        row.append("</tr>")

        return "\n".join(row)

    @staticmethod
    def correctly_format_codes(code):
        if isinstance(code, float) or isinstance(code, int):
            code = "%d" % code
        return code

    @staticmethod
    def correctly_format_rate(rate):
        if isinstance(rate, str):
            rate = "%f" % rate
        return rate

    @classmethod
    def update_rate_by_match(cls, overwrite=True, **kwargs):
        direction = kwargs.get('direction', OUTGOING)
        country_code = cls.correctly_format_codes(kwargs.get('country_code', ''))
        mcc = cls.correctly_format_codes(kwargs.get('mcc', ''))
        mnc = cls.correctly_format_codes(kwargs.get('mnc', ''))

        rate = cls.get_by_match(direction, country_code, mcc, mnc)
        print "attempted to fetch rate", rate
        if not rate:
            print "NO RATE FOUND"
            rate = MachSMSBillableRate()
            rate.direction = direction
            rate.country_code = country_code
            rate.mcc = mcc
            rate.mnc = mnc
            overwrite = True

        if overwrite:
            rate.currency_code = "EUR"
            rate.last_modified = datetime.datetime.utcnow()
            rate.base_fee = cls.correctly_format_rate(kwargs.get('base_fee', MACH_DEFAULT_BASE))
            rate.surcharge = cls.correctly_format_rate(kwargs.get('surcharge', 0))
            rate.country = kwargs.get('country', '')
            rate.network = kwargs.get('network', '')
            rate.iso = str(kwargs.get('iso', ''))

        rate.save()

        return rate


    @classmethod
    def get_by_match(cls, direction="I", country_code="", mcc="", mnc=""):
        key = [direction, country_code, mcc, mnc]
        print "KEY", key
        rate = MachSMSBillableRate.view('hqpayments/mach_rates',
            reduce=False,
            include_docs=True,
            startkey=key,
            endkey=key+[{}],
        ).first()
        print rate
        return rate

class TropoSMSBillableRate(SMSBillableRate):
    pass

class UnicelSMSBillableRate(SMSBillableRate):
    pass






