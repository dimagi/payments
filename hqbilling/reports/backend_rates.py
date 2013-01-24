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
    report_template_path = "hqbilling/reports/mach_rate_report.html"

    def _update_initial_context(self):
        if self.request.method == 'POST':
            self.asynchronous = False
        super(MachRateReport, self)._update_initial_context()

    @property
    def report_context(self):
        context = super(MachRateReport, self).report_context
        if self.request.method == 'POST':
            bulk_upload_form = MachExcelFileUploadForm(self.request.POST, self.request.FILES)
            if bulk_upload_form.is_valid():
                bulk_upload_form.save()
                bulk_upload_form = MachExcelFileUploadForm()
            else:
                messages.error(self.request, "Bulk Upload did not work.")
        else:
            bulk_upload_form = MachExcelFileUploadForm()
        context.update(mach_bulk_upload_form=bulk_upload_form)
        return context

    @property
    def headers(self):
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

    @property
    def headers(self):
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

    @property
    def headers(self):
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

    @property
    def headers(self):
        headers = DataTablesHeader(
            DataTablesColumn("Domain"),
            DataTablesColumn("Direction"),
            DataTablesColumn("Surcharge"),
            DataTablesColumn("Edit")
        )
        return headers