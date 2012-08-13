from django.contrib import messages
from corehq.apps.reports.datatables import DataTablesHeader, DataTablesColumn
from hqbilling.forms import MachExcelFileUploadForm, MachSMSRateForm, TropoSMSRateForm, \
    UnicelSMSRateForm, DimagiSMSRateForm
from hqbilling.models import MachSMSRate, TropoSMSRate, \
    DimagiDomainSMSRate, UnicelSMSRate
from hqbilling.reports import UpdatableItem

class MachRateReport(UpdatableItem):
    slug = "mach_rates"
    name = "MACH Rates"
    form_class = MachSMSRateForm
    item_class = MachSMSRate
    template_name = "hqbilling/reports/mach_rate_report.html"

    def get_parameters(self):
        if self.request.method == 'POST':
            bulk_upload_form = MachExcelFileUploadForm(self.request.POST, self.request.FILES)
            if bulk_upload_form.is_valid():
                bulk_upload_form.save()
                bulk_upload_form = MachExcelFileUploadForm()
            else:
                messages.error(self.request, "Bulk Upload did not work.")
        else:
            bulk_upload_form = MachExcelFileUploadForm()

        self.context.update(dict(
            mach_bulk_upload_form = bulk_upload_form
        ))

    def get_headers(self):
        headers = DataTablesHeader(
            DataTablesColumn("Direction"),
            DataTablesColumn("Country"),
            DataTablesColumn("Network"),
            DataTablesColumn("ISO"),
            DataTablesColumn("Country Code"),
            DataTablesColumn("MCC"),
            DataTablesColumn("MNC"),
            DataTablesColumn("Base Fee"),
            DataTablesColumn("Surcharge"),
            DataTablesColumn("Edit")
        )
        return headers

    @property
    def status_message(self):
        return "Currency is in <strong>&euro; EUR</strong>."

class TropoRateReport(UpdatableItem):
    slug = "tropo_rates"
    name = "Tropo Rates"
    form_class = TropoSMSRateForm
    item_class = TropoSMSRate

    def get_headers(self):
        headers = DataTablesHeader(
            DataTablesColumn("Direction"),
            DataTablesColumn("Country Code"),
            DataTablesColumn("Fee"),
            DataTablesColumn("Edit")
        )
        return headers

class UnicelRateReport(UpdatableItem):
    slug = "unicel_rates"
    name = "Unicel Rates"
    form_class = UnicelSMSRateForm
    item_class = UnicelSMSRate

    def get_headers(self):
        headers = DataTablesHeader(
            DataTablesColumn("Direction"),
            DataTablesColumn("Fee"),
            DataTablesColumn("Edit")
        )
        return headers

class DimagiRateReport(UpdatableItem):
    slug = "dimagi_rates"
    name = "Dimagi Surcharges Per Domain"
    form_class = DimagiSMSRateForm
    item_class = DimagiDomainSMSRate

    def get_headers(self):
        headers = DataTablesHeader(
            DataTablesColumn("Domain"),
            DataTablesColumn("Direction"),
            DataTablesColumn("Surcharge"),
            DataTablesColumn("Edit")
        )
        return headers