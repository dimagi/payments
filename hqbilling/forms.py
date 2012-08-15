from datetime import datetime
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.forms.util import ErrorList
from django.forms.widgets import HiddenInput, Select
from django.utils.safestring import mark_safe
import magic
from openpyxl.shared.exc import InvalidFileException
from dimagi.utils.excel import WorkbookJSONReader
from corehq.apps.hq_bootstrap.forms.widgets import BootstrapRadioSelect, \
    BootstrapAddressField, BootstrapPhoneNumberInput
from hqbilling.models import SMSRate, MachSMSRate, TropoSMSRate, UnicelSMSRate, DimagiDomainSMSRate, OUTGOING, \
    SMS_DIRECTIONS, INCOMING, DEFAULT_BASE, TaxRateByCountry, BillableCurrency

DIRECTION_CHOICES = ((OUTGOING, SMS_DIRECTIONS.get(OUTGOING),), (INCOMING, SMS_DIRECTIONS.get(INCOMING),))
DUPE_CHECK_NEW = "new"
DUPE_CHECK_EXISTING = "existing"

class DomainBillingInfoForm(forms.Form):
    currency_code = forms.ChoiceField(choices=[(settings.DEFAULT_CURRENCY, settings.DEFAULT_CURRENCY)])
    name = forms.CharField(label="Company Name", required=False)
    address = BootstrapAddressField(required=False)
    city = forms.CharField(label="City", required=False)
    state_province = forms.CharField(label="State/Province", required=False)
    postal_code = forms.CharField(label="Postal Code", required=False)
    country = forms.CharField(label="Country", required=False)
    phone_number = forms.CharField(widget=BootstrapPhoneNumberInput(), label="Phone Number", required=False)

    def __init__(self, data=None, files=None, auto_id='id_%s', prefix=None,
               initial=None, error_class=ErrorList, label_suffix=':',
               empty_permitted=False):
        super(DomainBillingInfoForm, self).__init__(data, files, auto_id, prefix, initial,
            error_class, label_suffix, empty_permitted)
        all_currencies = BillableCurrency.get_all()
        if all_currencies:
            self.fields['currency_code'].choices = [(cur.currency_code, mark_safe("%s %s" %
                                                                                  (cur.symbol, cur.currency_code)))
                                                                        for cur in all_currencies]

    def save(self, domain):
        params = self.cleaned_data
        domain.update_billing_info(**params)
        domain.save()

class ItemUpdateForm(forms.Form):

    def __init__(self, data=None, files=None, auto_id='id_%s', prefix=None,
                 initial=None, error_class=ErrorList, label_suffix=':',
                 empty_permitted=False, item_id=None):
        self.item_id = item_id
        super(ItemUpdateForm, self).__init__(data, files, auto_id, prefix, initial,
            error_class, label_suffix, empty_permitted)

    def save(self):
        return NotImplementedError

    @property
    def item_class(self):
        return NotImplementedError

    def update(self, rate):
        params = self.cleaned_data
        rate.update_item_from_form(**params)
        return [rate.as_row]

    def save(self):
        params = self.cleaned_data
        rate = self.item_class.get_or_create_new_from_form(**params)
        return [rate.as_row]


class BillableCurrencyUpdateForm(ItemUpdateForm):
    currency_code = forms.CharField(required=True, label="Currency Code (ex: USD)")
    symbol = forms.CharField(required=False, label="Symbol for currency (ex: $)")

    @property
    def item_class(self):
        return BillableCurrency

    def clean(self):
        cleaned_data = super(BillableCurrencyUpdateForm, self).clean()
        currency = BillableCurrency.get_by_code(cleaned_data.get("currency_code")).first()
        if currency and self.item_id is None:
            raise ValidationError("That currency code has already been used. Try editing that code directly")
        elif currency and self.item_id != currency.get_id:
            raise ValidationError("That currency code has already been used!")
        return cleaned_data


class TaxRateUpdateForm(ItemUpdateForm):
    country = forms.CharField(required=False, label="Country\n (or blank for any)")
    tax_rate = forms.DecimalField(required=True, label="Tax Rate %")

    @property
    def item_class(self):
        return TaxRateByCountry

    def clean(self):
        cleaned_data = super(TaxRateUpdateForm, self).clean()
        tax_rate = TaxRateByCountry.get_by_country(cleaned_data.get("country")).first()
        if tax_rate and self.item_id is None:
            raise ValidationError("A tax rate for the country %s already exists. Please edit that existing rate." %
                                  cleaned_data.get("country"))
        elif tax_rate and self.item_id != tax_rate.get_id:
            raise ValidationError("There is already a tax rate for that country.")
        return cleaned_data


class SMSRateForm(ItemUpdateForm):
    direction = forms.ChoiceField(widget=BootstrapRadioSelect, initial=OUTGOING, choices=DIRECTION_CHOICES)
    base_fee = forms.DecimalField(required=True, initial=DEFAULT_BASE, label="Fee")

    @property
    def item_class(self):
        return SMSRate

    def clean(self):
        cleaned_data = super(SMSRateForm, self).clean()
        rate_item = self.item_class.get_by_match(self.item_class.generate_match_key(**cleaned_data))
        if rate_item and self.item_id is None:
            raise ValidationError("A rate item like this already exists. Please edit that item instead.")
        elif rate_item and self.item_id != rate_item.get_id:
            raise ValidationError("You are making this rate the same as an existing one.")
        return cleaned_data


class MachSMSRateForm(SMSRateForm):
    network_surcharge = forms.DecimalField(required=False, label="Network Surcharge", initial=0)
    country = forms.CharField(required=True, label="Country")
    network = forms.CharField(required=True, label="Network")
    country_code = forms.CharField(required=False, label="Country Code")
    iso = forms.CharField(required=False, label="ISO")
    mcc = forms.CharField(required=False, label="MCC")
    mnc = forms.CharField(required=False, label="MNC")

    @property
    def item_class(self):
        return MachSMSRate


class TropoSMSRateForm(SMSRateForm):
    country_code = forms.CharField(required=False, label="Country Code (or blank for any)")

    @property
    def item_class(self):
        return TropoSMSRate


class UnicelSMSRateForm(SMSRateForm):
    @property
    def item_class(self):
        return UnicelSMSRate


class DimagiSMSRateForm(SMSRateForm):
    domain = forms.CharField(label="Project Name\n (blank for any)", required=False)

    @property
    def item_class(self):
        return DimagiDomainSMSRate


class MachExcelFileUploadForm(forms.Form):
    mach_file = forms.FileField(label="Rate Spreadsheet")
    overwrite = forms.BooleanField(label="Overwrite Existing Rates", initial=True)

    def clean_mach_file(self):
        if 'mach_file' in self.cleaned_data:
            mach_file = self.cleaned_data['mach_file']
            try:
                mach_file = WorkbookJSONReader(mach_file)
                mach_file = mach_file.get_worksheet()
            except InvalidFileException:
                raise forms.ValidationError("Please convert to Excel 2007 or higher (.xlsx) and try again.")
            except Exception as e:
                raise forms.ValidationError("Encountered error: %s" % e)
            return mach_file

    def save(self):
        mach_file = self.cleaned_data['mach_file']
        overwrite = self.cleaned_data['overwrite']
        for row in mach_file:
            row = dict([(key.split(' ')[0], val) for key, val in row.items()])
            rate = MachSMSRate.get_or_create_new_from_form(overwrite=overwrite, **row)
