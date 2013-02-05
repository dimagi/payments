import decimal
import datetime
from corehq.apps.crud.models import BaseAdminHQTabularCRUDManager
import settings

class BillableCurrencyCRUDManager(BaseAdminHQTabularCRUDManager):
    """
        CRUD Manager for Billable currencies
    """

    @property
    def properties_in_row(self):
        return ["currency_code", "symbol", "conversion", "last_updated"]

    def format_property(self, key, property):
        if isinstance(property, datetime.datetime):
            return property.strftime("%d %B %Y at %H:%M")
        if key == 'conversion':
            if settings.DEFAULT_CURRENCY != self.document_instance.currency_code:
                return "%s %s : 1 %s" % (property, settings.DEFAULT_CURRENCY, self.document_instance.currency_code)
            return "Default Currency"
        if isinstance(property, decimal.Decimal):
            property = property.quantize(decimal.Decimal(10) ** -4)
            return "%s" % property
        return super(BillableCurrencyCRUDManager, self).format_property(key, property)

    def update(self, **kwargs):
        currency_code = kwargs.get('currency_code', '')
        self.document_instance.last_updated = datetime.datetime.utcnow()
        default_currency = settings.DEFAULT_CURRENCY.upper()
        if currency_code == default_currency:
            self.document_instance.conversion = 1.0
            self.document_instance.source = "default"
        else:
            self.document_instance.set_live_conversion_rate(currency_code, default_currency)
        super(BillableCurrencyCRUDManager, self).update(**kwargs)

    def is_valid(self, existing=None, **kwargs):
        existing_doc = self.document_class.get_by_code(kwargs.get('currency_code', '')).first()
        if existing:
            return existing_doc._id == existing._id
        return not existing_doc


class TaxRateCRUDManager(BaseAdminHQTabularCRUDManager):
    """
        CRUD Manager for Tax Rates
    """
    @property
    def properties_in_row(self):
        return ["country", "tax_rate"]

    def format_property(self, key, property):
        if key == "tax_rate":
            return "%.4f%%" % property
        if key == "country":
            return property if property else "Applies to All Countries"
        return super(TaxRateCRUDManager, self).format_property(key, property)

    def is_valid(self, existing=None, **kwargs):
        existing_doc = self.document_class.get_by_country(kwargs.get('country', '')).first()
        if existing:
            return existing_doc._id == existing._id
        return not existing_doc


class SMSRateCRUDManager(BaseAdminHQTabularCRUDManager):
    """
        CRUD Manager for Billing Rates and ...
    """
    currency_character = "$"
    currency_code = settings.DEFAULT_CURRENCY

    @property
    def properties_in_row(self):
        return ["direction", "base_fee"]

    def format_property(self, key, property):
        if key == "direction":
            from hqbilling.models import SMS_DIRECTIONS
            return SMS_DIRECTIONS[property]
        if isinstance(property, decimal.Decimal):
            property = property.quantize(decimal.Decimal(10) ** -3)
            return "%s %s" % (self.currency_character, property)
        return super(SMSRateCRUDManager, self).format_property(key, property)

    def update(self, **kwargs):
        self.document_instance.last_modified = datetime.datetime.utcnow()
        self.document_instance.currency_code = self.currency_code
        super(SMSRateCRUDManager, self).update(**kwargs)

        print "BASE FEE", self.document_instance.base_fee

    def is_valid(self, existing=None, **kwargs):
        existing_doc = self.document_class.get_default(**kwargs)
        print existing_doc
        if existing and existing_doc:
            return existing_doc._id == existing._id
        return not existing_doc


class MachSMSRateCRUDManager(SMSRateCRUDManager):
    currency_character = "&euro;"
    currency_code = "EUR"

    @property
    def properties_in_row(self):
        return ["direction",
                "country",
                "network",
                "iso",
                "country_code",
                "mcc",
                "mnc",
                "base_fee",
                "network_surcharge"]


class TropoSMSRateCRUDManager(SMSRateCRUDManager):

    @property
    def properties_in_row(self):
        return ["direction",
                "country_code",
                "base_fee"]

    def format_property(self, key, property):
        if key == "country_code":
            return property if property else "Applies to All Non-Matching Projects"
        return super(TropoSMSRateCRUDManager, self).format_property(key, property)


class DimagiDomainSMSRateCRUDManager(SMSRateCRUDManager):

    @property
    def properties_in_row(self):
        return ["domain",
                "direction",
                "base_fee"]

    def format_property(self, key, property):
        if key == "domain":
            return property if property else "Applies to All Non-Matching Projects"
        return super(DimagiDomainSMSRateCRUDManager, self).format_property(key, property)
