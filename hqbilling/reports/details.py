from django.core.urlresolvers import reverse
from corehq.apps.reports.standard import DatespanMixin
from corehq.apps.reports.datatables import DataTablesColumn, DataTablesHeader, DTSortType, DataTablesColumnGroup
from corehq.apps.reports.generic import GenericTabularReport
from corehq.apps.reports import util as report_utils
from hqbilling.fields import SelectSMSDirectionField, SelectBilledDomainsField, SelectSMSBillableDomainsField
from hqbilling.models import MachSMSBillable, TropoSMSBillable, UnicelSMSBillable, HQMonthlyBill, SMS_DIRECTIONS, TaxRateByCountry, SMSBillable
from hqbilling.reports import HQBillingReport

class BillingDetailReport(GenericTabularReport, HQBillingReport, DatespanMixin):
    """
        Base class for Billing detail reports
    """
    project_filter_class = None

    _projects = None
    @property
    def projects(self):
        if self._projects is None:
            project = self.request.GET.get(self.project_filter_class.slug)
            all_projects = self.project_filter_class.get_billable_domains()
            self._projects = [project] if project else all_projects
        return self._projects

    def _format_bill_amount(self, amount):
        return self.table_cell(amount, "$ %.2f" % amount)


class SMSDetailReport(BillingDetailReport):
    name = "Messaging"
    slug = "sms_detail"
    fields = ['corehq.apps.reports.fields.DatespanField',
              'hqbilling.fields.SelectSMSBillableDomainsField',
              'hqbilling.fields.SelectSMSDirectionField']

    project_filter_class = SelectSMSBillableDomainsField

    _direction = None
    @property
    def direction(self):
        if self._direction is None:
            self._direction = self.request.GET.get(SelectSMSDirectionField.slug)
        return self._direction

    @property
    def headers(self):
        return DataTablesHeader(
            DataTablesColumn("Date"),
            DataTablesColumn("Project"),
            DataTablesColumn("Direction"),
            DataTablesColumn("Backend API"),
            DataTablesColumnGroup("Charges",
                DataTablesColumn("Backend Fee"),
                DataTablesColumn("Dimagi Fee"),
                DataTablesColumn("Total")
            )
        )

    @property
    def rows(self):
        rows = []
        totals = [0,0,0]
        for project in self.projects:
            if self.direction:
                billables = SMSBillable.by_domain_and_direction(project, self.direction,
                    start=self.datespan.startdate_param_utc, end=self.datespan.enddate_param_utc).all()
            else:
                billables = SMSBillable.by_domain(project,
                    start=self.datespan.startdate_param_utc, end=self.datespan.enddate_param_utc).all()
            for billable in billables:
                totals[0] += billable.converted_billable_amount
                totals[1] += billable.dimagi_surcharge
                totals[2] += billable.total_billed
                rows.append([
                    self.table_cell(billable.billable_date,
                        billable.billable_date.strftime("%B %d, %Y %H:%M:%S")),
                    project,
                    SMS_DIRECTIONS.get(billable.direction),
                    eval(billable.doc_type).api_name(),
                    self._format_bill_amount(billable.converted_billable_amount),
                    self._format_bill_amount(billable.dimagi_surcharge),
                    self._format_bill_amount(billable.total_billed)
                ])
        self.total_row = ["","","","Total Billed:"]+["%.2f" % t for t in totals]
        return rows


class MonthlyBillReport(BillingDetailReport):
    name = "Monthly Bill by Project"
    slug = "monthly_bill"
    fields = ['hqbilling.fields.DatespanBillingStartField',
              'hqbilling.fields.SelectBilledDomainsField']
    report_template_path = "hqbilling/reports/monthly_bill_summary_report.html"
    exportable = False

    project_filter_class = SelectBilledDomainsField

    @property
    def headers(self):
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

    @property
    def rows(self):
        rows = []
        payment_button_template = """<a href="#changePaymentStatusModal"
        onclick="payment_status.updateModalForm('%(bill_id)s')"
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
                    self.table_cell(
                        bill.billing_period_start,
                        nice_start
                    ),
                    self.table_cell(
                        bill.billing_period_end,
                        nice_end
                    ),
                    self._format_bill_amount(bill.incoming_sms_billed),
                    self._format_bill_amount(bill.outgoing_sms_billed),
                    self._format_bill_amount(bill.incoming_sms_billed+bill.outgoing_sms_billed),
                    len(bill.active_users),
                    bill.active_users_billed,
                    self._format_bill_amount(bill.incoming_sms_billed+bill.outgoing_sms_billed+bill.active_users_billed),
                    self.table_cell(
                        int(bill.paid),
                        payment_button_template % dict(
                            bill_id=bill.get_id,
                            payment_status="yes" if bill.paid else "no",
                            payment_status_text="Paid" if bill.paid else "Not Paid",
                            button_class="btn-success paid" if bill.paid else "btn-danger",
                            billing_start=nice_start,
                            billing_end=nice_end,
                            domain=project
                        )
                    ),
                    '<a href="%s" class="btn btn-primary">View Invoice</a>' %
                        reverse("billing_invoice", kwargs=dict(bill_id=bill.get_id)),
                    '<a href="%s" class="btn"><i class="icon icon-list"></i> View Itemized</a>' %
                        reverse("billing_itemized", kwargs=dict(bill_id=bill.get_id))
                ])

        return rows
