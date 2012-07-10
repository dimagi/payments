from datetime import datetime
from django import forms
import magic
from openpyxl.shared.exc import InvalidFileException
from dimagi.utils.excel import WorkbookJSONReader
from hqpayments.models import MachSMSBillableRate, MACH_DEFAULT_BASE

class MachBillableItemForm(forms.Form):
    country_code = forms.CharField(required=True, label="Country Code")
    iso = forms.CharField(required=True, label="ISO")
    country = forms.CharField(required=True, label="Country")
    mcc = forms.CharField(required=True, label="MCC")
    mnc = forms.CharField(label="MNC")
    network = forms.CharField(required=True, label="Network")
    base_fee = forms.DecimalField(required=True, initial=MACH_DEFAULT_BASE, label="Base Fee")
    surcharge = forms.DecimalField(required=False, label="Surcharge")

    def save(self):
        direction = self.data['direction']

        params = self.cleaned_data
        params['direction'] = direction if direction else "O"

        rate = MachSMSBillableRate.update_rate_by_match(**params)

        return rate

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
            rate = MachSMSBillableRate.update_rate_by_match(overwrite=overwrite, **row)
