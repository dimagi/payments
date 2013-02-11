from django.contrib import messages
from django.utils.safestring import mark_safe
from corehq.apps.reports.datatables import DataTablesHeader, DataTablesColumn
from hqbilling.forms import MachExcelFileUploadForm, MachSMSRateForm, TropoSMSRateForm, \
    UnicelSMSRateForm, DimagiSMSRateForm
from hqbilling.models import MachSMSRate, TropoSMSRate, \
    DimagiDomainSMSRate, UnicelSMSRate
from hqbilling.reports import BaseBillingAdminInterface

class BaseSMSRateReport(BaseBillingAdminInterface):

    @property
    def rates(self):
        key = ["all", self.document_class.__name__]
        data = self.document_class.view('hqbilling/sms_rates',
            reduce=False,
            include_docs=True,
            startkey=key,
            endkey=key+[{}]
        ).all()
        return data

    @property
    def rows(self):
        rows = []
        for rate in self.rates:
            rows.append(rate.admin_crud.row)
        return rows


class MachRateReport(BaseSMSRateReport):
    slug = "mach_rates"
    name = "MACH Rates"

    crud_item_type = "Mach Rate"
    document_class = MachSMSRate
    form_class = MachSMSRateForm

    report_template_path = "hqbilling/reports/mach_rate_report.html"

    detailed_description = mark_safe("""<p>The currency for Mach Rates is <strong>&euro; EUR</strong></p>
        <p>The base rate for Mach is &euro; 0.005.</p>
        <p>You may upload Mach rates in bulk using the following form:
            <a href="#bulkUploadRateModal"
                class="btn" data-toggle="modal">Upload Rates in Bulk</a>
        </p>""")

    def _update_initial_context(self):
        if self.request.method == 'POST':
            self.asynchronous = False
        super(MachRateReport, self)._update_initial_context()

    _bulk_upload_form = None
    @property
    def bulk_upload_form(self):
        if self._bulk_upload_form is None:
            self._bulk_upload_form = MachExcelFileUploadForm()
        return self._bulk_upload_form

    @property
    def report_context(self):
        context = super(MachRateReport, self).report_context
        if self.request.method == 'POST':
            bulk_upload_form = MachExcelFileUploadForm(self.request.POST, self.request.FILES)
            if bulk_upload_form.is_valid():
                bulk_upload_form.save()
                bulk_upload_form = MachExcelFileUploadForm()
                messages.success(self.request, mark_safe('Bulk Upload was successful<br />' \
                                                         '<a class="btn btn-success" href="%s">Refresh ' \
                                                         'to View New Rates</a>' % self.get_url()))
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
    def rows(self):
        return super(MachRateReport, self).rows

class TropoRateReport(BaseSMSRateReport):
    slug = "tropo_rates"
    name = "Tropo Rates"

    document_class = TropoSMSRate
    form_class = TropoSMSRateForm

    detailed_description = mark_safe("""
        <p>Tropo rates are in USD.</p>
    """)

    @property
    def headers(self):
        headers = DataTablesHeader(
            DataTablesColumn("Direction"),
            DataTablesColumn("Country Code"),
            DataTablesColumn("Fee"),
            DataTablesColumn("Edit")
        )
        return headers


class UnicelRateReport(BaseSMSRateReport):
    slug = "unicel_rates"
    name = "Unicel Rates"

    document_class = UnicelSMSRate
    form_class = UnicelSMSRateForm

    detailed_description = mark_safe("""
        <p>Tropo rates are in USD.</p>
    """)

    @property
    def headers(self):
        headers = DataTablesHeader(
            DataTablesColumn("Direction"),
            DataTablesColumn("Fee"),
            DataTablesColumn("Edit")
        )
        return headers


class DimagiRateReport(BaseSMSRateReport):
    slug = "dimagi_rates"
    name = "Dimagi Surcharges Per Domain"

    document_class = DimagiDomainSMSRate
    form_class = DimagiSMSRateForm

    detailed_description = mark_safe("""
        <p>This fee is added on top of any SMS provider's rates.</p>
    """)

    description = "Dimagi's fee applied on top of other SMS backend fees."

    @property
    def headers(self):
        headers = DataTablesHeader(
            DataTablesColumn("Domain"),
            DataTablesColumn("Direction"),
            DataTablesColumn("Surcharge"),
            DataTablesColumn("Edit")
        )
        return headers
