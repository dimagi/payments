from datetime import datetime
from django import forms
from django.forms.util import ErrorList
import magic
from openpyxl.shared.exc import InvalidFileException
from dimagi.utils.excel import WorkbookJSONReader
from hqpayments.models import *
from corehq.apps.hq_bootstrap.forms.widgets import BootstrapRadioSelect

DIRECTION_CHOICES = (('O', 'Outgoing',), ('I', 'Incoming',))

class BillableItemForm(forms.Form):
    direction = forms.ChoiceField(widget=BootstrapRadioSelect, initial='O', choices=DIRECTION_CHOICES)
    base_fee = forms.DecimalField(required=True, initial=DEFAULT_BASE, label="Base Fee")
    surcharge = forms.DecimalField(required=False, label="Surcharge")

    @property
    def billable_item_type(self):
        return 'SMSBillableRate'

    def save(self):
        params = self.cleaned_data
        rate_type = eval(self.billable_item_type)
        rate = rate_type.update_rate_by_match(**params)
        return [rate.as_row]

    def update(self, rate):
        params = self.cleaned_data
        rate.update_rate(**params)
        return [rate.as_row]

class MachBillableItemForm(BillableItemForm):
    country_code = forms.CharField(required=True, label="Country Code")
    iso = forms.CharField(required=True, label="ISO")
    country = forms.CharField(required=True, label="Country")
    mcc = forms.CharField(required=True, label="MCC")
    mnc = forms.CharField(label="MNC")
    network = forms.CharField(required=True, label="Network")

    @property
    def billable_item_type(self):
        return 'MachSMSBillableRate'


class TropoBillableItemForm(BillableItemForm):
    domain = forms.CharField(required=True, label="Project Name (Domain)")

    @property
    def billable_item_type(self):
        return 'TropoSMSBillableRate'


class UnicelBillableItemForm(BillableItemForm):

    @property
    def billable_item_type(self):
        return 'UnicelSMSBillableRate'


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
            rate = MachSMSBillableRate.update_rate_by_match(overwrite=overwrite, **row)
            print rate.as_row
