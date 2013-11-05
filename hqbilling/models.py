# Stub models file
import calendar
import logging
import re
from couchdbkit.ext.django.schema import *
import datetime
import decimal
from django.conf import settings
import urllib2
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
import phonenumbers
import pytz
from corehq.apps.crud.models import AdminCRUDDocumentMixin
from corehq.apps.reports.util import make_form_couch_key
from corehq.apps.users.models import CommCareUser
from dimagi.utils.couch.database import get_db
from dimagi.utils.dates import add_months
from dimagi.utils.decorators.memoized import memoized
from dimagi.utils.modules import to_function
from dimagi.utils.timezones import utils as tz_utils
from hqbilling.crud import (SMSRateCRUDManager, DimagiDomainSMSRateCRUDManager, MachSMSRateCRUDManager,
                            TropoSMSRateCRUDManager, BillableCurrencyCRUDManager, TaxRateCRUDManager)
from hqbilling.utils import get_mach_data, format_start_end_suffixes

from corehq.apps.unicel.api import UnicelBackend
from corehq.apps.tropo.api import TropoBackend
from corehq.apps.mach.api import MachBackend

DEFAULT_BASE = 0.02
MACH_BASE_RATE = 0.005
ACTIVE_USER_RATE = 0.75
UNKNOWN_RATE_ID = "UNKNOWN"
INCOMING = "I"
OUTGOING = "O"
SMS_DIRECTIONS = {
    INCOMING: "Incoming",
    OUTGOING: "Outgoing"
}
INCOMING_MSG_ID = "incoming"

class HQMonthlyBill(Document):
    """
        This bill is auto-generated by a periodic celery task for the previous month
        starting at midnight on the first of each month.
    """
    domain = StringProperty()

    billing_period_start = DateTimeProperty()
    billing_period_end = DateTimeProperty()
    date_generated = DateTimeProperty()

    incoming_sms_billables = ListProperty()
    incoming_sms_billed = DecimalProperty(default=0)

    outgoing_sms_billables = ListProperty()
    outgoing_sms_billed = DecimalProperty(default=0)

    # these are currently not being used...waiting on pricing scheme to emerge
    active_users = ListProperty()
    active_users_billed = DecimalProperty(default=0)

    paid = BooleanProperty(default=False)

    @property
    @memoized
    def domain_object(self):
        from corehq.apps.domain.models import Domain
        return Domain.get_by_name(self.domain)

    @property
    @memoized
    def currency(self):
        currency_code = self.domain_object.currency_code if hasattr(self.domain_object, 'currency_code') else None
        if not currency_code:
            currency_code = settings.DEFAULT_CURRENCY
        return BillableCurrency.get_by_code(currency_code).first()

    @property
    @memoized
    def tax(self):
        tax_rate = TaxRateByCountry.get_by_country(self.domain_object.billing_address.country).first()
        if not tax_rate:
            tax_rate = TaxRateByCountry.get_default()
        return tax_rate

    @property
    def invoice_id(self):
        """
            If anyone can think of a better id system than this, let me know.
            Using the doc id would look a little 'scary' to the average user,
            this at least has some meaningful pattern.
        """
        parts = list()
        parts_date_fmt = "%m%d%Y"
        parts.append(self.domain.upper()[0:3])
        parts.append(self.billing_period_start.strftime(parts_date_fmt))
        parts.append(self.billing_period_end.strftime(parts_date_fmt))
        parts.append(self.date_generated.strftime(parts_date_fmt))
        return "".join(parts)

    @property
    def subtotal(self):
        return self.incoming_sms_billed + self.outgoing_sms_billed + self.active_users_billed

    @property
    def subtotal_formatted(self):
        return self._fmt_cost(self.subtotal)

    @property
    def tax_rate(self):
        return self.tax.tax_rate

    @property
    def tax_applied(self):
        return (self.tax_rate/100) * self.subtotal

    @property
    def total_billed(self):
        return self.subtotal + self.tax_applied

    @property
    def html_billing_address(self):
        if hasattr(self.domain_object, 'billing_address') \
           and self.domain_object.billing_address and self.domain_object.billing_address.country:
            return self.domain_object.billing_address.html_address
        else:
            return mark_safe("""<address><strong>Project '%s'</strong><br />
                        No address available. Please ask project administrator to enter one.</address>""" %
                             self.domain)

    @property
    def html_dimagi_address(self):
        country = self.domain_object.billing_address.country
        address = render_to_string("hqbilling/partials/dimagi_address.html", {
            'is_india':  country and country.lower() == 'india',
        })
        return address

    @property
    def invoice_items(self):
        items = list()
#        if self.active_users_billed > 0:
#            items.append(dict(
#                desc="CommCare HQ Hosting Fees",
#                qty="%s users" % len(self.active_users),
#                unit_price=self._fmt_cost(decimal.Decimal(ACTIVE_USER_RATE)),
#                billed=self._fmt_cost(self.active_users_billed)
#            ))
        if self.incoming_sms_billed > 0:
            items.append(dict(
                desc="SMS Inbound",
                qty=len(self.incoming_sms_billables),
                unit_price="See Itemized List for Details",
                billed=self._fmt_cost(self.incoming_sms_billed)
            ))
        if self.outgoing_sms_billed > 0:
            items.append(dict(
                desc="SMS Outbound",
                qty=len(self.outgoing_sms_billables),
                unit_price="See Itemized List for Details",
                billed=self._fmt_cost(self.outgoing_sms_billed)
            ))
        return items

    @property
    def invoice_total(self):
        return [self._fmt_cost(self.subtotal),
            "%.2f%%" % self.tax_rate,
            self._fmt_cost(self.tax_applied),
            mark_safe('<strong style="font-size:1.5em;">%s</strong>' % self._fmt_cost(self.total_billed))
        ]

    @property
    def itemized_statement(self):
        itemized = dict()
        if self.incoming_sms_billed > 0:
            itemized.update(dict(
                incoming_sms=dict(
                    messages=self._itemized_sms(INCOMING),
                    total_text="Total for Inbound Messages",
                    total=self._fmt_cost(self.incoming_sms_billed)
                )
            ))
        if self.outgoing_sms_billed > 0:
            itemized.update(dict(
                outgoing_sms=dict(
                    messages=self._itemized_sms(OUTGOING),
                    total_text="Total for Outbound Messages",
                    total=self._fmt_cost(self.outgoing_sms_billed)
                )
            ))
#        if self.active_users_billed > 0:
#            itemized.update(dict(
#                users=self._itemized_users(),
#                users_total=self._fmt_cost(self.total_billed)
#            ))
        return itemized

    def _itemized_sms(self, direction):
        direction_name = SMS_DIRECTIONS.get(direction).lower()
        sms_ids = getattr(self, "%s_sms_billables" % direction_name)
        itemized = list()
        for sms_id in sms_ids:
            billable = SMSBillable.get_correct_wrap(sms_id)
            itemized.append([
                billable.billable_date.strftime("%d %b %Y %H:%M"),
                billable.phone_number,
                billable.api_name(),
                self._fmt_cost(billable.total_billed)
            ])
        return itemized

    def _itemized_users(self):
        itemized = list()
        for user_id in self.active_users:
            user = CommCareUser.get(user_id)
            key = make_form_couch_key(self.domain, user_id=user_id)
            all_submissions = get_db().view('reports_forms/all_forms',
                reduce=True,
                startkey=key,
                endkey=key+[{}]
            ).first()
            all_submissions = all_submissions.get('value', 0) if all_submissions else 0
            itemized.append([
                user.username_in_report,
                all_submissions,
                self._fmt_cost(decimal.Decimal(ACTIVE_USER_RATE))
            ])
        return itemized

    def _fmt_cost(self, cost):
        return mark_safe("%s %.2f" % (self.currency.safe_symbol, cost/self.currency.safe_conversion))

    def _get_all_active_and_submitted_users(self):
        """
            Active users are:
            1) All CommCareUser objects who have the is_active flag set to True at the time of this bill generation.
            2) All CommCareUser objects who have the is_active flag set to False at the time of this bill generation
                but have submitted things to CommCare HQ during the span of the billing period.
        """
        from corehq.apps.users.models import CommCareUser
        active_user_ids = [user.user_id for user in CommCareUser.by_domain(self.domain)]
        inactive_user_ids = [user.user_id for user in CommCareUser.by_domain(self.domain, is_active=False)]

        key = make_form_couch_key(self.domain)
        data = get_db().view('reports_forms/all_forms',
            reduce=False,
            startkey = key+[self.billing_period_start.isoformat()],
            endkey = key+[self.billing_period_end.isoformat()]
        ).all()
        submitted_user_ids = [item.get('value',{}).get('user_id') for item in data]
        inactive_submitted_user_ids = list(set([user_id for user_id in submitted_user_ids
                                                if user_id in inactive_user_ids]))
        
        self.active_users = active_user_ids+inactive_submitted_user_ids

    def _get_sms_activities(self, direction):
        direction_name = SMS_DIRECTIONS.get(direction).lower()
        all_billables = SMSBillable.by_domain_and_direction(self.domain,
            direction, start=self.billing_period_start.isoformat(),
            end=self.billing_period_end.isoformat())
        all_ids = [b.get_id for b in all_billables]
        cost = sum([b.total_billed for b in all_billables])
        setattr(self, '%s_sms_billables' % direction_name, all_ids)
        setattr(self, '%s_sms_billed' % direction_name, cost)

    @classmethod
    def get_default_start_end(cls):
        # Last month's date range
        today = datetime.datetime.utcnow()
        (last_month_year, last_month) = add_months(today.year, today.month, -1)
        (_, last_day) = calendar.monthrange(last_month_year, last_month)
        start_date = datetime.datetime(today.year, last_month, 1, hour=0, minute=0, second=0, microsecond=0)
        end_date = datetime.datetime(today.year, last_month, last_day,
                                     hour=23, minute=59, second=59, microsecond=999999)
        return start_date, end_date

    def new_bill(self, billing_range=None):
        start = billing_range[0] if billing_range else None
        end = billing_range[1] if billing_range else None
        if not (isinstance(start, datetime.datetime) and isinstance(end, datetime.datetime)):
            start, end = self.get_default_start_end()

        self.billing_period_start = start
        self.billing_period_end = end
        self.date_generated = datetime.datetime.utcnow()

        self._get_sms_activities(INCOMING)
        self._get_sms_activities(OUTGOING)

#        self._get_all_active_and_submitted_users()
#        if len(self.active_users) > 20:
#            self.active_users_billed = len(self.active_users) * ACTIVE_USER_RATE

    @classmethod
    def get_bills(cls, domain, prefix="start", paid=None, start=None, end=None, include_docs=True):
        extra = []
        if paid is not None:
            prefix = "%s paid"
        if paid is True:
            extra = ["yes"]
        elif paid is False:
            extra = ["no"]
        key = [prefix, domain]+extra
        startkey_suffix, endkey_suffix = format_start_end_suffixes(start, end)
        return cls.view("hqbilling/monthly_bills",
            include_docs=include_docs,
            reduce=False,
            startkey=key+startkey_suffix,
            endkey=key+endkey_suffix
        )

    @classmethod
    def create_bill_for_domain(cls, domain, billing_range=None):
        bill = cls(domain=domain)
        bill.new_bill(billing_range)
        if bill.incoming_sms_billed > 0 or bill.outgoing_sms_billed > 0:
            # save only the bills with costs attached so that there isn't a long list
            # of non-actionable bills at the end
            bill.save()
            logging.info("[BILLING] Bill for domain %s was created." % domain)
        else:
            logging.info("[BILLING] No Bill for domain %s was created. "
                         "The there was no billable amount for outgoing or incoming SMS" % domain)
        return bill


class BillableCurrency(Document, AdminCRUDDocumentMixin):
    currency_code = StringProperty()
    symbol = StringProperty()
    conversion = DecimalProperty()
    source = StringProperty()
    last_updated = DateTimeProperty()

    _admin_crud_class = BillableCurrencyCRUDManager

    @property
    def safe_symbol(self):
        return self.symbol if self.symbol else "$"

    @property
    def safe_conversion(self):
        return self.conversion if self.conversion != 0 else 1

    def set_live_conversion_rate(self, from_currency, to_currency):
        conversion_url = "http://www.google.com/ig/calculator?hl=en&q=1%s=?%s" % (from_currency, to_currency)
        try:
            data = urllib2.urlopen(conversion_url).read()
            # AGH GOOGLE WHY DON'T YOU RETURN VALID JSON??? ?#%!%!%@#
            rhs = re.compile('rhs:\s*"([^"]+)"')
            data = rhs.search(data).group()
            cur = re.compile('[0-9.]+')
            data = cur.search(data).group()
            self.conversion = float(data)
        except Exception as e:
            self.conversion = 0.0
            logging.error("[Billing] There was an error retrieving the conversion rate from %s to %s using %s: %s"
                          % (from_currency, to_currency, conversion_url, e))
            conversion_url = "ERROR: %s, %s" % (e, conversion_url)
        self.source = conversion_url

    _currency_view = "hqbilling/currencies"
    @classmethod
    def get_by_code(cls, currency_code, include_docs=True):
        key = [currency_code.upper()]
        return cls.view(cls._currency_view,
            reduce=False,
            include_docs=include_docs,
            startkey=key,
            endkey=key+[{}]
        )

    @classmethod
    def get_all(cls, include_docs=True):
        return cls.view(cls._currency_view,
            reduce=False,
            include_docs=include_docs
        )

    @classmethod
    def get_existing_or_new_by_code(cls, currency_code):
        currency = cls.get_by_code(currency_code).first()
        if not currency:
            currency_code = currency_code.upper()
            currency = cls(currency_code=currency_code)
            currency.save()
        return currency


class TaxRateByCountry(Document, AdminCRUDDocumentMixin):
    """
        Holds the tax rate by country name (case insensitive).
    """
    country = StringProperty(default="")
    tax_rate = DecimalProperty(default=0)

    _admin_crud_class = TaxRateCRUDManager

    @classmethod
    def get_by_country(cls, country, include_docs=True):
        return cls.view("hqbilling/tax_rates",
            reduce=False,
            include_docs=include_docs,
            startkey=[country],
            endkey=[country, {}]
        )

    @classmethod
    def get_default(cls, include_docs=True):
        return cls.get_by_country("", include_docs).first()


class SMSRate(Document, AdminCRUDDocumentMixin):
    direction = StringProperty()
    last_modified = DateTimeProperty()
    currency_code = StringProperty(default=settings.DEFAULT_CURRENCY)
    base_fee = DecimalProperty()

    _admin_crud_class = SMSRateCRUDManager

    def __str__(self):
        return "%s | direction: %s | amt: %s %.3f" % (self.__class__.__name__,
                                                      SMS_DIRECTIONS.get(self.direction, "Unknown"),
                                                      self.currency_code,
                                                      self.billable_amount)

    @property
    def default_base_fee(self):
        return DEFAULT_BASE

    @property
    def billable_amount(self):
        return self.base_fee

    @property
    def conversion_rate(self):
        rate = 0.0
        try:
            r = BillableCurrency.get_by_code(self.currency_code).first()
            rate = r.conversion
        except Exception as e:
            logging.error("Could not get conversion rate. Error: %s" % e)
        return decimal.Decimal(rate)

    @classmethod
    def get_default(cls, direction=None, **kwargs):
        key = ["type", cls.__name__, direction or OUTGOING] + cls._make_key(**kwargs)
        return cls._get_by_key(key)

    @classmethod
    def _make_key(cls, **kwargs):
        return []

    @classmethod
    def _get_by_key(cls, key, include_docs=True):
        return cls.view("hqbilling/sms_rates",
            reduce=False,
            include_docs=include_docs,
            startkey=key,
            endkey=key+[{}]
        ).first()


class MachSMSRate(SMSRate):
    """
        Generated with each inbound/outbound sms via Mach's API.
    """
    country_code = StringProperty()
    country = StringProperty()
    iso = StringProperty()
    mcc = StringProperty()
    mnc = StringProperty()
    network = StringProperty()
    network_surcharge = DecimalProperty(default=0)

    _admin_crud_class = MachSMSRateCRUDManager

    def __str__(self):
        return "%s | network: %s | country: %s" % (super(MachSMSRate, self).__str__(), self.network, self.country)

    @property
    def billable_amount(self):
        return self.base_fee + self.network_surcharge

    @classmethod
    def _make_key(cls, **kwargs):
        return [kwargs.get("country", ""),
                kwargs.get("network", "")]

    @classmethod
    def get_by_number(cls, direction, mach_number):
        return cls.get_default(direction, country=mach_number.country, network=mach_number.network)


class TropoSMSRate(SMSRate):
    """
        This is a billing rate for SMSs sent via Tropo.
    """
    country_code = StringProperty()

    _admin_crud_class = TropoSMSRateCRUDManager

    @classmethod
    def _make_key(cls, **kwargs):
        return [kwargs.get('country_code', '')]


class UnicelSMSRate(SMSRate):
    pass


class DimagiDomainSMSRate(SMSRate):
    """
        This is the Dimagi SMS surcharge configured on a per domain level
    """
    domain = StringProperty()

    _admin_crud_class = DimagiDomainSMSRateCRUDManager

    @classmethod
    def _make_key(cls, **kwargs):
        return [kwargs.get('domain', "")]


class MachPhoneNumber(Document):
    phone_number = StringProperty()
    network = StringProperty()
    country = StringProperty()

    def __str__(self):
        return "MACH Phone Number (%s) | Country: %s | Network: %s" % (self.phone_number, self.country, self.network)

    @classmethod
    def get_by_number(cls, number, api_info):
        try:
            [country, network] = api_info[-2].strip().split('  ')
        except Exception:
            country = None
            network = None
        try:
            mach_number = cls.view("hqbilling/mach_phone_numbers",
                reduce=False,
                include_docs=True,
                startkey=[number],
                endkey=[number,{}]
            ).first()
            if not mach_number:
                mach_number = cls()
            if country and network:
                mach_number.phone_number = number
                mach_number.country = country
                mach_number.network = network
                mach_number.save()
            return mach_number
        except Exception as e:
            logging.error("Error retrieving mach phone number: %s" % e)
            return None


class SMSBillable(Document):
    """
        One of these is generated every time an SMS is successfully sent or received.
        The cost is generated at the time the SMS is sent or received.
    """
    billable_date = DateTimeProperty()
    modified_date = DateTimeProperty()

    # billable amount is not converted into USD, stays in the billing rate's currency
    # this is the amount that the SMS backend is billing Dimagi
    billable_amount = DecimalProperty()

    # conversion rate at the time of creating the billable item
    # this applies only to the billable amount
    conversion_rate = DecimalProperty()

    # the dimagi surcharge is always in USD and is the amount we may or may not add on top of the billable amount
    # based on the domain used
    dimagi_surcharge = DecimalProperty(default=0)

    rate_id = StringProperty()
    log_id = StringProperty()

    # Summary Info
    domain = StringProperty()
    direction = StringProperty()
    phone_number = StringProperty()

    has_error = BooleanProperty(default=False)
    error_message = StringProperty()

    def __str__(self):
        return "Billable for %s SMS | direction: %s | domain: %s | total: %s" % \
               (self.api_name(), SMS_DIRECTIONS.get(self.direction, "Unknown"), self.domain, self.total_billed)

    @property
    def converted_billable_amount(self):
        if self.billable_amount:
            return self.billable_amount * self.conversion_rate
        return 0

    @property
    def total_billed(self):
        return self.converted_billable_amount + self.dimagi_surcharge

    @property
    def default_rate_item(self):
        # Note: Not all rates have a default available
        return None

    @property
    def throw_error_on_rateless(self):
        return True

    def calculate_surcharge(self, message):
        dimagi_rate = DimagiDomainSMSRate.get_default(direction=message.direction, domain=message.domain)
        if not dimagi_rate:
            # default rate
            dimagi_rate = DimagiDomainSMSRate.get_default(message.direction, domain="")
        self.dimagi_surcharge = dimagi_rate.base_fee if dimagi_rate else 0
        logging.info("[Billing] Dimagi Surcharge of $%.3f applied" % self.dimagi_surcharge)

    def calculate_rate(self, rate_item, real_time=True):
        if rate_item is None:
            rate_item = self.default_rate_item

        if rate_item:
            self.billable_amount = rate_item.billable_amount
            self.conversion_rate = rate_item.conversion_rate
            if self.conversion_rate == 0:
                # TEMPORARY FIX
                # for EUR conversion so that pathfinder can get billed immediately
                self.conversion_rate = 1.38
            self.rate_id = rate_item._id
            logging.info("[Billing] Successfully Applied SMS Rate: %s" % rate_item)
        else:
            self.rate_id = UNKNOWN_RATE_ID
            self.conversion_rate = 1
            self.billable_amount = 0
            if self.throw_error_on_rateless:
                self.has_error = True
                self.error_message = "Could not find rate item to match message or API response."
                logging.error("[Billing] No SMS Rate Item Found for SMSLog # %s | %s | %s" %
                              (self.log_id, self._id, self))

        if real_time or self.billable_date is None:
            self.billable_date = datetime.datetime.utcnow()
        self.modified_date = datetime.datetime.utcnow()

    def save_message_info(self, message):
        self.log_id = message.get_id
        self.domain = message.domain
        self.direction = message.direction
        self.phone_number = message.phone_number
        logging.info("[Billing] Billable saved from message from/to %s with SMS direction %s, SMSLog #%s" %
                     (self.domain, SMS_DIRECTIONS.get(self.direction, "unknown"), self.log_id))

    @classmethod
    def _get_docs(cls, startkey, endkey, include_docs=True):
        return cls.view("hqbilling/sms_billables",
            include_docs=include_docs,
            reduce=False,
            startkey=startkey,
            endkey=endkey
        ).all()

    @classmethod
    def _get_relevant_classes(cls):
        return cls.__subclasses__() if cls == SMSBillable else [cls]

    @classmethod
    def get_correct_wrap(cls, docid):
        data = cls.get_db().get(docid)
        try:
            correct_class = to_function("hqbilling.models.%s" % data['doc_type'])
        except Exception:
            correct_class = cls
        return correct_class.get(docid)

    @classmethod
    def get_all(cls, include_docs=True):
        data = []
        for c in cls._get_relevant_classes():
            key = ["type domain", c.__name__]
            data.extend(c._get_docs(key, key+[{}], include_docs=include_docs))
        return data

    @classmethod
    def by_domain(cls, domain, include_docs=True, start=None, end=None):
        data = []
        for c in cls._get_relevant_classes():
            key = ["type domain", c.__name__, domain]
            startkey_suffix, endkey_suffix = format_start_end_suffixes(start, end)
            data.extend(c._get_docs(key+startkey_suffix, key+endkey_suffix, include_docs=include_docs))
        return data

    @classmethod
    def by_domain_and_direction(cls, domain, direction, include_docs=True, start=None, end=None):
        data = []
        for c in cls._get_relevant_classes():
            key = ["type domain direction", c.__name__, domain, direction]
            startkey_suffix, endkey_suffix = format_start_end_suffixes(start, end)
            data.extend(c._get_docs(key+startkey_suffix, key+endkey_suffix, include_docs=include_docs))
        return data

    @classmethod
    def handle_api_response(cls, message, **kwargs):
        return NotImplementedError("Each API must be handled specifically, due to variations in responses.")

    @classmethod
    def new_billable(cls, rate_item, message):
        logging.info("[Billing] New Billable for %s" % cls.api_name())
        billable = cls()
        billable.save_message_info(message)
        billable.calculate_surcharge(message)
        billable.calculate_rate(rate_item)
        billable.save()
        return billable

    @staticmethod
    def api_name():
        return "All"


class UnicelSMSBillable(SMSBillable):
    """
        Generated when an SMS is sent or received via Unicel's API.
    """
    unicel_id = StringProperty()

    @classmethod
    def handle_api_response(cls, message, **kwargs):
        response = kwargs.get('response', None)
        logging.info("[Billing] Unicel API Response %s" % response)
        rate_item = UnicelSMSRate.get_default(direction=message.direction)
        if message.direction == INCOMING:
            billable = cls.new_billable(rate_item, message)
            if billable:
                billable.unicel_id = INCOMING_MSG_ID
                billable.save()
                return
        elif isinstance(response, str) and len(response) > 0:
            # attempt to figure out if there was an error in sending the message.
            # Look for something like '0x200 - ' in the returned string
            # A successful return will just be a uuid from Unicel.
            find_err = re.compile('\dx\d\d\d\s-\s')
            match = find_err.search(response)
            if not match:
                billable = cls.new_billable(rate_item, message)
                if billable:
                    billable.unicel_id = response
                    billable.save()
                    return
        logging.error("[Billing] Did not successfully bill Unicel Message with ID # %s" % message.get_id)

    @staticmethod
    def api_name():
        return "Unicel"


class TropoSMSBillable(SMSBillable):
    """
        Generated when an SMS is sent via Tropo's API.
    """
    tropo_id = StringProperty()

    @property
    def default_rate_item(self):
        return TropoSMSRate.get_default(self.direction or OUTGOING, country_code="")

    @classmethod
    def handle_api_response(cls, message, **kwargs):
        response = kwargs.get("response")
        logging.info("[Billing] Tropo API Response %s" % response)
        number = phonenumbers.parse(message.phone_number)
        rate_item = TropoSMSRate.get_default(direction=message.direction, country_code="%d" % number.country_code)
        if message.direction == INCOMING:
            billable = cls.new_billable(rate_item, message)
            if billable:
                billable.tropo_id = INCOMING_MSG_ID
                billable.save()
                return
        else:
            find_success = re.compile('(<success>).*(</success>)')
            match = find_success.search(response)
            successful = bool(match and match.group() == '<success>true</success>')
            if successful:
                billable = cls.new_billable(rate_item, message)
                if billable:
                    billable.tropo_id = cls.get_tropo_id(response)
                    billable.save()
                    return
        logging.error("[Billing] Did not successfully bill Tropo Message with ID # %s" % message.get_id)

    @classmethod
    def get_tropo_id(cls, response):
        id_reg = re.compile('(<id>[a-zA-Z0-9][a-zA-Z0-9][a-zA-Z0-9]+)')
        match = id_reg.search(response)
        if match and len(match.group()) > 4:
            return match.group()[4:]
        return None

    @staticmethod
    def api_name():
        return "Tropo"


class MachSMSBillable(SMSBillable):
    """
        Generated when an SMS is sent or received via Mach's API.
    """
    contacted_mach_api = DateTimeProperty()
    sync_attempts = ListProperty()
    mach_delivery_status = StringProperty()
    mach_id = StringProperty()
    mach_delivered_date = DateTimeProperty()

    @property
    def default_rate_item(self):
        return MachSMSRate.get_default(self.direction or OUTGOING, country="", network="")

    @property
    def throw_error_on_rateless(self):
        """
            If there is actually a delivered date, then throw an error here.
        """
        return self.mach_delivered_date is not None

    def save_message_info(self, message):
        self.sync_attempts.append(datetime.datetime.utcnow())
        super(MachSMSBillable, self).save_message_info(message)

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
                existing = self.get_by_mach_id(mach_id)
                # allowing three minutes of latency and making sure that the mach_id is unique
                if total_seconds <= 60*3 and not existing:
                    self.mach_id = mach_id
                    self.mach_delivery_status = delivery_status
                    self.mach_delivered_date = delivered_on
            except Exception as e:
                logging.info("[Billing] Error parsing MACH API delivery info: %s" % e)
        elif delivery_status == 'accepted':
            # message has not been delivered yet
            self.mach_id = mach_id
            self.mach_delivery_status = delivery_status

    _mach_couchview = "hqbilling/mach_billables"
    @classmethod
    def get_by_mach_id(cls, mach_id, include_docs=True):
        return cls.view(cls._mach_couchview,
            reduce=False,
            include_docs=include_docs,
            startkey=["by mach_id", mach_id],
            endkey=["by mach_id", mach_id, {}]
        )

    @classmethod
    def get_rateless(cls, include_docs=True):
        return cls.view(cls._mach_couchview,
            reduce=False,
            include_docs=include_docs,
            startkey=["rateless"],
            endkey=["rateless", {}]
        )

    @classmethod
    def get_statusless(cls, include_docs=True):
        return cls.view(cls._mach_couchview,
            reduce=False,
            include_docs=include_docs,
            startkey=["statusless"],
            endkey=["statusless", {}]
        )

    @classmethod
    def handle_api_response(cls, message, **kwargs):
        response = kwargs.get('response', None)
        logging.info("[Billing] Mach API Response %s" % response)
        # temporary measure, charge all messages
        rate_item = MachSMSRate.get_default(direction=OUTGOING, country="USA", network="dimagi")
        billable = cls.new_billable(rate_item, message)
        if billable:
            now = datetime.datetime.now(tz=pytz.utc)
            billable.contacted_mach_api = now
            billable.mach_id = "dimagi-retro"
            billable.mach_delivery_status = "delivered"
            billable.mach_delivered_date = now
            from corehq.apps.sms.models import SMSLog
            msg = SMSLog.get(message._id)  # no doc conflicts
            msg.billed = True
            msg.save()
            # make sure the billable_date is the same date the message was generated for retro billing issues.
            billable.billable_date = message.date
            billable.save()
            return
        if isinstance(response, str) or isinstance(response, unicode):
            api_success = bool("+OK" in response)
            if api_success:
                test_mach_data = kwargs.get('_test_scrape')
                mach_data = test_mach_data if test_mach_data else get_mach_data()
                for mach_row in mach_data:
                    phone_number = mach_row[3]
                    if phone_number != message.phone_number:
                        continue

                    mach_number = MachPhoneNumber.get_by_number(message.phone_number, mach_row)
                    rate_item = MachSMSRate.get_by_number(message.direction, mach_number) if mach_number else None

                    billable = cls.new_billable(rate_item, message)
                    if billable:
                        billable.contacted_mach_api = datetime.datetime.now(tz=pytz.utc)
                        billable.update_mach_delivery_status(mach_row)
                        billable.save()
                        return
                    logging.error("[Billing] MACH API Response was successful, but creating the MACH "
                                  "billable was not. SMSLog # %s" % message.get_id)
                else:
                    logging.error("[Billing] There was an error retrieving message delivery information from MACH.")
            else:
                logging.error("[Billing] There was an error accessing the MACHI API.")
        else:
            logging.error("[Billing] There was an error while trying to send an SMS via MACH.")

    @staticmethod
    def api_name():
        return "Mach"


API_TO_BILLABLE = {
    UnicelBackend.get_api_id(): UnicelSMSBillable,
    TropoBackend.get_api_id(): TropoSMSBillable,
    MachBackend.get_api_id(): MachSMSBillable,
}
