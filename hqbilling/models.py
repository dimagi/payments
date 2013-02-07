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
from dimagi.utils.decorators.memoized import memoized
from dimagi.utils.modules import to_function
from dimagi.utils.timezones import utils as tz_utils
from hqbilling.crud import (SMSRateCRUDManager, DimagiDomainSMSRateCRUDManager, MachSMSRateCRUDManager,
                            TropoSMSRateCRUDManager, BillableCurrencyCRUDManager, TaxRateCRUDManager)
from hqbilling.utils import get_mach_data, format_start_end_suffixes

DEFAULT_BASE = 0.02
ACTIVE_USER_RATE = 0.75
INCOMING = "I"
OUTGOING = "O"
SMS_DIRECTIONS = {
    INCOMING: "Incoming",
    OUTGOING: "Outgoing"
}

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

    def _get_default_start_end(self):
        today = datetime.datetime.utcnow()
        td = datetime.timedelta(days=14)
        two_weeks = today - td
        billing_month = two_weeks.month
        billing_year = two_weeks.year
        (_, last_day) = calendar.monthrange(billing_year, billing_month)
        start_date = datetime.datetime(billing_year, billing_month, 1, 0, 0, 0, 0)
        end_date = datetime.datetime(billing_year, billing_month, last_day, 23, 59, 59, 999999)
        return start_date, end_date

    def new_bill(self, billing_range=None):
        start = billing_range[0] if billing_range else None
        end = billing_range[1] if billing_range else None
        if not (isinstance(start, datetime.datetime) and isinstance(end, datetime.datetime)):
            start, end = self._get_default_start_end()

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

        if bill.incoming_sms_billed > 0 or \
           bill.outgoing_sms_billed > 0:
            # save only the bills with costs attached so that there isn't a long list
            # of non-actionable bills at the end
            bill.save()
            logging.info("[BILLING] Bill for project %s was created." % domain)
        else:
            logging.info("[BILLING] No Bill for project %s was created." % domain)
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
    network_surcharge = DecimalProperty()

    _admin_crud_class = MachSMSRateCRUDManager

    @property
    def billable_amount(self):
        return self.base_fee + self.network_surcharge

    @classmethod
    def _make_key(cls, **kwargs):
        return [kwargs.get("country", ""),
                kwargs.get("network", "")]

    @classmethod
    def get_by_number(cls, direction, mach_number, include_docs=True):
        key = ["type", cls.__name__, direction, mach_number.network, mach_number.country]
        return cls._get_by_key(key)


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

    @property
    def converted_billable_amount(self):
        return self.billable_amount * self.conversion_rate

    @property
    def total_billed(self):
        return self.converted_billable_amount + self.dimagi_surcharge

    def _calculate_surcharge(self, message):
        match_key = DimagiDomainSMSRate.generate_match_key(**dict(
            direction=message.direction,
            domain=message.domain
        ))
        dimagi_rate = DimagiDomainSMSRate.get_by_match(match_key)
        if not dimagi_rate:
            dimagi_rate = DimagiDomainSMSRate.get_default_rate(message.direction)
        self.dimagi_surcharge = dimagi_rate.base_fee if dimagi_rate else 0

    def calculate_rate(self, rate_item, message, real_time=True):
        if rate_item:
            if real_time or self.billable_date is None:
                self.billable_date = datetime.datetime.utcnow()
            self.modified_date = datetime.datetime.utcnow()
            self.billable_amount = rate_item.billable_amount
            self.conversion_rate = rate_item.conversion_rate
            self.rate_id = rate_item._id
            self._calculate_surcharge(message)
            message.billed = True
            message.save()

    def save_message_info(self, message):
        self.log_id = message.get_id
        self.domain = message.domain
        self.direction = message.direction
        self.phone_number = message.phone_number

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
        for doc_type in cls._get_doc_types():
            key = ["type domain direction", doc_type, domain, direction]
            startkey_suffix, endkey_suffix = format_start_end_suffixes(start, end)
            data.extend(cls._get_docs(key+startkey_suffix, key+endkey_suffix, include_docs=include_docs))
        return data

    @classmethod
    def handle_api_response(cls, message, **kwargs):
        if message.billing_errors:
            logging.error("ERRORS billing SMS Message with ID %s:\n%s" % (message._id, "\n".join(message.billing_errors)))
            message.save()

    @classmethod
    def save_from_message(cls, rate_item, message):
        billable = None
        if rate_item:
            billable = cls()
            billable.calculate_rate(rate_item, message)
            billable.save_message_info(message)
            billable.save()
        else:
            message.billing_errors.append("Billing rate entry could not be found.")
        return dict(billable=billable, message=message)

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
        match_key = UnicelSMSRate.generate_match_key(**dict(direction=message.direction))
        rate_item = UnicelSMSRate.get_by_match(match_key)
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
        super(UnicelSMSBillable, cls).handle_api_response(message, **kwargs)

    @staticmethod
    def api_name():
        return "Unicel"


class TropoSMSBillable(SMSBillable):
    """
        Generated when an SMS is sent via Tropo's API.
    """
    tropo_id = StringProperty()

    @classmethod
    def handle_api_response(cls, message, **kwargs):
        response = kwargs.get("response")
        find_success = re.compile('(<success>).*(</success>)')
        match = find_success.search(response)
        successful = bool(match and match.group() == '<success>true</success>')
        if successful:
            number = phonenumbers.parse(message.phone_number)
            rate_item = TropoSMSRate.get_by_match(
                TropoSMSRate.generate_match_key(**dict(direction=message.direction,
                    country_code="%d" % number.country_code
                )))
            if not rate_item:
                rate_item = TropoSMSRate.get_default_rate(message.direction).first()
            result = cls.save_from_message(rate_item, message)
            billable = result.get('billable', None)
            if billable:
                billable.tropo_id = cls.get_tropo_id(response)
                billable.save()
        else:
            message.billing_errors.append("An error occurred while sending a message through the Tropo API.")
        super(TropoSMSBillable, cls).handle_api_response(message, **kwargs)

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
                logging.info("Error parsing mach API delivery info: %s" % e)
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
        if isinstance(response, str) or isinstance(response, unicode):
            api_success = bool("+OK" in response)
            if api_success:
                test_mach_data = kwargs.get('_test_scrape')
                mach_data = test_mach_data if test_mach_data else get_mach_data()
                if mach_data:
                    last_message = mach_data[0]
                    phone_number = last_message[3]
                    billable = cls()
                    billable.save_message_info(message)
                    billable.contacted_mach_api = datetime.datetime.now(tz=pytz.utc)
                    if phone_number == message.phone_number:
                        # same phone number, now check delivery date
                        billable.update_mach_delivery_status(last_message)
                    mach_number = MachPhoneNumber.get_by_number(message.phone_number, last_message)
                    if mach_number:
                        rate_item = MachSMSRate.get_by_number(message.direction, mach_number)
                        billable.calculate_rate(rate_item, message)
                    billable.save()
                else:
                    message.billing_errors.append("There was an error retrieving message delivery information from Mach.")
            else:
                message.billing_errors.append("There was an error accessing the MACHI API.")
        else:
            message.billing_errors.append("There was an error while trying to send an SMS to via Mach.")
        super(MachSMSBillable, cls).handle_api_response(message, **kwargs)

    @staticmethod
    def api_name():
        return "Mach"
