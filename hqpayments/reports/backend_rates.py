from django.contrib import messages
from corehq.apps.reports.datatables import DataTablesHeader, DataTablesColumn
from corehq.apps.reports.standard import StandardTabularHQReport, StandardHQReport
from hqpayments.forms import MachExcelFileUploadForm
from hqpayments.models import *
from hqpayments.reports.billing import HQBillingReport

class HQBillingRateReport(HQBillingReport, StandardTabularHQReport):
    template_name = "hqpayments/billing/reports/rate_report.html"
    fields = []
    hide_filters = True
    exportable = False

    rate_form_class = 'BillableItemForm'
    rate_item_class = 'SMSBillableRate'

    def get_default_report_url(self):
        return "#"

    def get_global_params(self):
        super(HQBillingRateReport, self).get_global_params()

    def get_report_context(self):
        super(HQBillingRateReport, self).get_report_context()
        self.context.update(dict(
            rate_form = dict(
                name=self.rate_form_class,
                item=self.rate_item_class
            ),
            rate_status_message=self.rate_status_message
        ))

    def get_rows(self):
        rate_type = eval(self.rate_item_class)
        all_rates = rate_type.view(rate_type.match_view(),
            reduce=False,
            include_docs=True
        ).all()
        return [rate.as_row for rate in all_rates]

    @property
    def rate_status_message(self):
        return "Default base rate is $1.00. Currency is in <strong>USD</strong>."

class MachRateReport(HQBillingRateReport):
    slug = "mach_rates"
    name = "MACH Rates"
    rate_form_class = 'MachBillableItemForm'
    rate_item_class = 'MachSMSBillableRate'
    template_name = "hqpayments/billing/reports/mach_rate_report.html"

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
            DataTablesColumn("Country Code"),
            DataTablesColumn("ISO"),
            DataTablesColumn("Country"),
            DataTablesColumn("MCC"),
            DataTablesColumn("MNC"),
            DataTablesColumn("Network"),
            DataTablesColumn("Base Fee"),
            DataTablesColumn("Surcharge"),
            DataTablesColumn("Direction"),
            DataTablesColumn("Edit")
        )
        return headers

    @property
    def rate_status_message(self):
        return "Default base rate is &euro;1.00. Currency is in <strong>EUR</strong>."

class TropoRateReport(HQBillingRateReport):
    slug = "tropo_rates"
    name = "Tropo Rates"
    rate_form_class = 'TropoBillableItemForm'
    rate_item_class = 'TropoSMSBillableRate'

    def get_headers(self):
        headers = DataTablesHeader(
            DataTablesColumn("Domain"),
            DataTablesColumn("Direction"),
            DataTablesColumn("Base Fee"),
            DataTablesColumn("Surcharge"),
            DataTablesColumn("Edit")
        )
        return headers

class UnicelRateReport(HQBillingRateReport):
    slug = "unicel_rates"
    name = "Unicel Rates"
    rate_form_class = 'UnicelBillableItemForm'
    rate_item_class = 'UnicelSMSBillableRate'

    def get_headers(self):
        headers = DataTablesHeader(
            DataTablesColumn("Direction"),
            DataTablesColumn("Base Fee"),
            DataTablesColumn("Surcharge"),
            DataTablesColumn("Edit")
        )
        return headers