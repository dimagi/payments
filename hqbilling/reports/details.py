from django.core.urlresolvers import reverse
from corehq.apps.reports.datatables import DataTablesColumn, DataTablesHeader, DTSortType, DataTablesColumnGroup
from corehq.apps.reports.standard import StandardTabularHQReport, StandardHQReport, StandardDateHQReport
from corehq.apps.reports import util as report_utils
from hqbilling.fields import SelectSMSDirectionField, SelectBilledDomainsField
from hqbilling.models import MachSMSBillable, TropoSMSBillable, UnicelSMSBillable, HQMonthlyBill, SMS_DIRECTIONS, TaxRateByCountry, SMSBillable
from hqbilling.reports import HQBillingReport

def format_bill_amount(amount):
    return report_utils.format_datatables_data(text="$ %.2f" % amount, sort_key=amount)

class DetailReportsMixin(object):

    def _get_projects(self, request):
        project = request.GET.get(SelectBilledDomainsField.slug)
        all_projects = SelectBilledDomainsField.get_billable_domains()
        self.projects = [project] if project else all_projects

class SMSDetailReport(HQBillingReport, StandardTabularHQReport, StandardDateHQReport, DetailReportsMixin):
    name = "Messaging"
    slug = "sms_detail"
    fields = ['corehq.apps.reports.fields.DatespanField',
              'hqbilling.fields.SelectSMSBillableDomainsField',
              'hqbilling.fields.SelectSMSDirectionField']

    def get_parameters(self):
        self._get_projects(self.request)
        self.direction = self.request.GET.get(SelectSMSDirectionField.slug)
        self.totals = [0,0,0]

    def get_headers(self):
        return DataTablesHeader(
            DataTablesColumn("Date", span=2),
            DataTablesColumn("Project", span=3),
            DataTablesColumn("Direction", span=2),
            DataTablesColumn("Backend API", span=2),
            DataTablesColumnGroup("Charges",
                DataTablesColumn("Backend Fee", span=1),
                DataTablesColumn("Dimagi Fee", span=1),
                DataTablesColumn("Total", span=1)
            )
        )

    def get_rows(self):
        rows = []
        for project in self.projects:
            if self.direction:
                billables = SMSBillable.by_domain_and_direction(project, self.direction,
                    start=self.datespan.startdate_param_utc, end=self.datespan.enddate_param_utc).all()
            else:
                billables = SMSBillable.by_domain(project,
                    start=self.datespan.startdate_param_utc, end=self.datespan.enddate_param_utc).all()
            for billable in billables:
                self.totals[0] += billable.converted_billable_amount
                self.totals[1] += billable.dimagi_surcharge
                self.totals[2] += billable.total_billed
                rows.append([
                    report_utils.format_datatables_data(
                        billable.billable_date.strftime("%B %d, %Y %H:%M:%S"),
                        billable.billable_date
                    ),
                    project,
                    SMS_DIRECTIONS.get(billable.direction),
                    eval(billable.doc_type).api_name(),
                    format_bill_amount(billable.converted_billable_amount),
                    format_bill_amount(billable.dimagi_surcharge),
                    format_bill_amount(billable.total_billed)
                ])
        self.total_row = ["","","","Total Billed:"]+["%.2f" % t for t in self.totals]
        return rows


class MonthlyBillReport(HQBillingReport, StandardTabularHQReport, StandardDateHQReport, DetailReportsMixin):
    name = "Monthly Bill by Project"
    slug = "monthly_bill"
    fields = ['hqbilling.fields.DatespanBillingStartField',
              'hqbilling.fields.SelectBilledDomainsField']
    template_name = "hqbilling/reports/monthly_bill_summary_report.html"
    exportable = False

    def get_parameters(self):
        self._get_projects(self.request)

    def get_headers(self):
        return DataTablesHeader(DataTablesColumn("Project"),
            DataTablesColumnGroup("Billing Period",
                DataTablesColumn("Start"),
                DataTablesColumn("End"),
            ),
            DataTablesColumnGroup("Messaging Expenses",
                DataTablesColumn("Incoming"),
                DataTablesColumn("Outgoing"),
                DataTablesColumn("Total")
            ),
            DataTablesColumnGroup("Hosting Expenses",
                DataTablesColumn("# Active Users"),
                DataTablesColumn("Total Charges")
            ),
            DataTablesColumn("Total Bill"),
            DataTablesColumn("Paid"),
            DataTablesColumn("Invoice", sortable=False),
            DataTablesColumn("Itemized", sortable=False)
        )

    def get_rows(self):
        rows = []

        payment_button_template = """<a href="#changePaymentStatusModal" onclick="payment_status.updateModalForm('%(bill_id)s')"
        id="update-%(bill_id)s" data-toggle="modal" class="btn %(button_class)s"
        data-domain="%(domain)s" data-billingstart="%(billing_start)s" data-billingend="%(billing_end)s">
    %(payment_status_text)s
</a>"""

        for project in self.projects:
            all_bills = HQMonthlyBill.get_bills(project,
                start=self.datespan.startdate_param_utc,
                end=self.datespan.enddate_param_utc
            ).all()
            for bill in all_bills:
                nice_start = bill.billing_period_start.strftime("%B %d, %Y")
                nice_end = bill.billing_period_end.strftime("%B %d, %Y")
                rows.append([
                    project,
                    report_utils.format_datatables_data(
                        nice_start,
                        bill.billing_period_start
                    ),
                    report_utils.format_datatables_data(
                        nice_end,
                        bill.billing_period_end
                    ),
                    format_bill_amount(bill.incoming_sms_billed),
                    format_bill_amount(bill.outgoing_sms_billed),
                    format_bill_amount(bill.incoming_sms_billed+bill.outgoing_sms_billed),
                    len(bill.active_users),
                    bill.active_users_billed,
                    format_bill_amount(bill.incoming_sms_billed+bill.outgoing_sms_billed+bill.active_users_billed),
                    report_utils.format_datatables_data(
                        text=payment_button_template % dict(
                            bill_id=bill.get_id,
                            payment_status="yes" if bill.paid else "no",
                            payment_status_text="Paid" if bill.paid else "Not Paid",
                            button_class="btn-success paid" if bill.paid else "btn-danger",
                            billing_start=nice_start,
                            billing_end=nice_end,
                            domain=project
                        ),
                        sort_key=int(bill.paid)
                    ),
                    '<a href="%s" class="btn btn-primary">View Invoice</a>' % reverse("billing_invoice", kwargs=dict(bill_id=bill.get_id)),
                    '<a href="%s" class="btn"><i class="icon icon-list"></i> View Itemized</a>' % reverse("billing_itemized", kwargs=dict(bill_id=bill.get_id))
                ])

        return rows
