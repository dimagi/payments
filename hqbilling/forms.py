from datetime import datetime
from django import forms
from django.core.exceptions import ValidationError
from django.forms.util import ErrorList
from django.forms.widgets import HiddenInput
import magic
from openpyxl.shared.exc import InvalidFileException
from dimagi.utils.excel import WorkbookJSONReader
from corehq.apps.hq_bootstrap.forms.widgets import BootstrapRadioSelect, BootstrapAddressField, BootstrapPhoneNumberInput
from hqbilling.models import SMSRate, MachSMSRate, TropoSMSRate, UnicelSMSRate, DimagiDomainSMSRate, OUTGOING, SMS_DIRECTIONS, INCOMING, DEFAULT_BASE, TaxRateByCountry

DIRECTION_CHOICES = ((OUTGOING, SMS_DIRECTIONS.get(OUTGOING),), (INCOMING, SMS_DIRECTIONS.get(INCOMING),))
DUPE_CHECK_NEW = "new"
DUPE_CHECK_EXISTING = "existing"

class DomainBillingInfoForm(forms.Form):
    name = forms.CharField(label="Company Name", required=False)
    address = BootstrapAddressField(required=False)
    city = forms.CharField(label="City", required=False)
    state_province = forms.CharField(label="State/Province", required=False)
    postal_code = forms.CharField(label="Postal Code", required=False)
    country = forms.CharField(label="Country", required=False)
    phone_number = forms.CharField(widget=BootstrapPhoneNumberInput(), label="Phone Number", required=False)

    def save(self, domain):
        print type(domain)
        from corehq.apps.domain.models import Domain
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

    def update(self, rate):
        params = self.cleaned_data
        rate.update_item_from_form(**params)
        return [rate.as_row]


class TaxRateUpdateForm(ItemUpdateForm):
    country = forms.CharField(required=False, label="Country (or blank for any)")
    tax_rate = forms.DecimalField(required=True, label="Tax Rate %")

    def clean(self):
        cleaned_data = super(TaxRateUpdateForm, self).clean()
        tax_rate = TaxRateByCountry.get_by_country(cleaned_data.get("country")).first()
        if tax_rate and self.item_id is None:
            raise ValidationError("A tax rate for the country %s already exists. Please edit that existing rate." % cleaned_data.get("country"))
        elif tax_rate and self.item_id != tax_rate.get_id:
            raise ValidationError("You are making this tax rate the same as an existing one.")
        return cleaned_data

    def save(self):
        params = self.cleaned_data
        rate = TaxRateByCountry.update_item_from_form(**params)
        return [rate.as_row]


class SMSRateForm(ItemUpdateForm):
    direction = forms.ChoiceField(widget=BootstrapRadioSelect, initial=OUTGOING, choices=DIRECTION_CHOICES)
    base_fee = forms.DecimalField(required=True, initial=DEFAULT_BASE, label="Fee")

    @property
    def billable_rate_class(self):
        return SMSRate

    def clean(self):
        cleaned_data = super(SMSRateForm, self).clean()
        rate_item = self.billable_rate_class.get_by_match(self.billable_rate_class.generate_match_key(**cleaned_data))
        if rate_item and self.item_id is None:
            raise ValidationError("A rate item like this already exists. Please edit that item instead.")
        elif rate_item and self.item_id != rate_item.get_id:
            raise ValidationError("You are making this rate the same as an existing one.")
        return cleaned_data

    def save(self):
        params = self.cleaned_data
        rate = self.billable_rate_class.update_item_from_form_by_match(**params)
        return [rate.as_row]


class MachSMSRateForm(SMSRateForm):
    network_surcharge = forms.DecimalField(required=False, label="Network Surcharge", initial=0)
    country = forms.CharField(required=True, label="Country")
    network = forms.CharField(required=True, label="Network")
    country_code = forms.CharField(required=False, label="Country Code")
    iso = forms.CharField(required=False, label="ISO")
    mcc = forms.CharField(required=False, label="MCC")
    mnc = forms.CharField(required=False, label="MNC")
    @property
    def billable_rate_class(self):
        return MachSMSRate


class TropoSMSRateForm(SMSRateForm):
    country_code = forms.CharField(required=False, label="Country Code (or blank for any)")
    @property
    def billable_rate_class(self):
        return TropoSMSRate


class UnicelSMSRateForm(SMSRateForm):
    @property
    def billable_rate_class(self):
        return UnicelSMSRate


class DimagiSMSRateForm(SMSRateForm):
    domain = forms.CharField(label="Project Name")
    @property
    def billable_rate_class(self):
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
            rate = MachSMSRate.update_item_from_form_by_match(overwrite=overwrite, **row)
            print rate.as_row
