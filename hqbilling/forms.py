from django import forms
from django.conf import settings
from django.forms.util import ErrorList
from django.utils.safestring import mark_safe
from openpyxl.shared.exc import InvalidFileException
from corehq.apps.crud.models import BaseAdminCRUDForm
from dimagi.utils.excel import WorkbookJSONReader
from hqstyle.forms.widgets import BootstrapRadioSelect, \
    BootstrapAddressField, BootstrapPhoneNumberInput
from hqbilling.models import (SMSRate, MachSMSRate, TropoSMSRate, UnicelSMSRate, DimagiDomainSMSRate, OUTGOING,
    SMS_DIRECTIONS, INCOMING, DEFAULT_BASE, TaxRateByCountry, BillableCurrency)

DIRECTION_CHOICES = ((OUTGOING, SMS_DIRECTIONS.get(OUTGOING),), (INCOMING, SMS_DIRECTIONS.get(INCOMING),))
DUPE_CHECK_NEW = "new"
DUPE_CHECK_EXISTING = "existing"


class SMSRateForm(BaseAdminCRUDForm):
    doc_class = SMSRate

    # fields
    direction = forms.ChoiceField(widget=BootstrapRadioSelect, initial=OUTGOING, choices=DIRECTION_CHOICES)
    base_fee = forms.DecimalField(required=True, initial=DEFAULT_BASE, label="Fee")


class MachSMSRateForm(SMSRateForm):
    doc_class = MachSMSRate

    # fields
    network_surcharge = forms.DecimalField(required=False, label="Network Surcharge", initial=0)
    country = forms.CharField(required=True, label="Country")
    network = forms.CharField(required=True, label="Network")
    country_code = forms.CharField(required=False, label="Country Code")
    iso = forms.CharField(required=False, label="ISO")
    mcc = forms.CharField(required=False, label="MCC")
    mnc = forms.CharField(required=False, label="MNC")


class TropoSMSRateForm(SMSRateForm):
    doc_class = TropoSMSRate

    # fields
    country_code = forms.CharField(required=False, label="Country Code (or blank for any)")


class UnicelSMSRateForm(SMSRateForm):
    doc_class = UnicelSMSRate


class DimagiSMSRateForm(SMSRateForm):
    doc_class = DimagiDomainSMSRate

    #fields
    domain = forms.CharField(label="Project Name\n (blank for any)", required=False)


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


class BillableCurrencyUpdateForm(BaseAdminCRUDForm):
    doc_class = BillableCurrency

    currency_code = forms.CharField(required=True, label="Currency Code (ex: USD)")
    symbol = forms.CharField(required=False, label="Symbol for currency (ex: $)")


class TaxRateUpdateForm(BaseAdminCRUDForm):
    doc_class = TaxRateByCountry

    country = forms.CharField(required=False, label="Country\n (or blank for any)")
    tax_rate = forms.DecimalField(required=True, label="Tax Rate %")


class MachExcelFileUploadForm(forms.Form):
    mach_file = forms.FileField(label="Rate Spreadsheet")
    overwrite = forms.BooleanField(label="Overwrite Existing Rates", initial=True, required=False)

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
            mach_rate = MachSMSRate.get_default(**row)

            # clean up parser
            for k in ['mcc', 'country_code', 'mnc']:
                row[k] = str(row[k])

            for k in ['network_surcharge']:
                val = row[k] or 0.0
                print val
                row[k] = "%f" % val

            if mach_rate and not overwrite:
                continue
            if not mach_rate:
                mach_rate = MachSMSRate()
            for key, item in row.items():
                try:
                    setattr(mach_rate, key, item)
                except AttributeError:
                    pass
            mach_rate.save()
