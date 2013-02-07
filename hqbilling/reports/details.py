from django.core.urlresolvers import reverse
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from corehq.apps.reports.standard import DatespanMixin
from corehq.apps.reports.datatables import DataTablesColumn, DataTablesHeader, DataTablesColumnGroup
from corehq.apps.reports.generic import GenericTabularReport
from dimagi.utils.decorators.memoized import memoized
from hqbilling.fields import SelectSMSDirectionField, SelectBilledDomainsField, SelectSMSBillableDomainsField
from hqbilling.models import HQMonthlyBill, SMS_DIRECTIONS, SMSBillable
from hqbilling.reports import HQBillingReport

class BillingDetailReport(GenericTabularReport, HQBillingReport, DatespanMixin):
    """
        Base class for Billing detail reports
    """
    project_filter_class = None

    @property
    @memoized
    def projects(self):
        project = self.request.GET.get(self.project_filter_class.slug)
        all_projects = self.project_filter_class.get_billable_domains()
        return [project] if project else all_projects

    def _format_bill_amount(self, amount):
        return self.table_cell(amount, "$ %.2f" % amount)


class SMSDetailReport(BillingDetailReport):
    name = "Messaging Details"
    slug = "sms_detail"
    fields = ['corehq.apps.reports.fields.DatespanField',
              'hqbilling.fields.SelectSMSBillableDomainsField',
              'hqbilling.fields.SelectSMSDirectionField']
    exportable = True

    project_filter_class = SelectSMSBillableDomainsField

    description = "See all the SMS messages sent during a time frame, per domain, and per direction."

    @property
    @memoized
    def direction(self):
        return self.request.GET.get(SelectSMSDirectionField.slug)

    @property
    def headers(self):
        return DataTablesHeader(
            DataTablesColumn("Date"),
            DataTablesColumn("Project"),
            DataTablesColumn("Direction"),
            DataTablesColumn("Backend API"),
            DataTablesColumnGroup("Fee Breakdown",
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
                    start=self.datespan.startdate_param_utc, end=self.datespan.enddate_param_utc)
            else:
                billables = SMSBillable.by_domain(project,
                    start=self.datespan.startdate_param_utc, end=self.datespan.enddate_param_utc)

            for billable in billables:
                totals[0] += billable.converted_billable_amount
                totals[1] += billable.dimagi_surcharge
                totals[2] += billable.total_billed
                rows.append([
                    self.table_cell(billable.billable_date,
                        billable.billable_date.strftime("%B %d, %Y %H:%M:%S")),
                    project,
                    SMS_DIRECTIONS.get(billable.direction),
                    billable.api_name(),
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
                DataTablesColumn("Outgoing")
            ),
            DataTablesColumn("Total Bill (USD)"),
            DataTablesColumn("Currency of Bill"),

            DataTablesColumn("Paid"),
            DataTablesColumn("Invoice", sortable=False),
            DataTablesColumn("Itemized", sortable=False)
        )

    @property
    def rows(self):
        rows = []

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
                    bill.currency.currency_code,
                    self.table_cell(
                        int(bill.paid),
                        mark_safe(render_to_string("hqbilling/partials/paid_button.html", {
                            'payment_status': "yes" if bill.paid else "no",
                            'bill_id': bill.get_id,
                            'payment_status_text': "Paid" if bill.paid else "Not Paid",
                            'button_class': "btn-success paid" if bill.paid else "btn-danger",
                            'billing_start': nice_start,
                            'billing_end': nice_end,
                            'domain': project,
                        }))
                    ),
                    mark_safe('<a href="%s" class="btn btn-primary">View Invoice</a>' %
                        reverse("billing_invoice", kwargs=dict(bill_id=bill.get_id))),
                    mark_safe('<a href="%s" class="btn"><i class="icon icon-list"></i> View Itemized</a>' %
                        reverse("billing_itemized", kwargs=dict(bill_id=bill.get_id)))
                ])

        return rows
