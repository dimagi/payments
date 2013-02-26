from django.core.urlresolvers import reverse
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from corehq.apps.domain.models import Domain
from corehq.apps.reports.standard import DatespanMixin
from corehq.apps.reports.datatables import DataTablesColumn, DataTablesHeader, DataTablesColumnGroup, DTSortType
from corehq.apps.reports.generic import GenericTabularReport
from dimagi.utils.dates import DateSpan
from dimagi.utils.decorators.memoized import memoized
from hqbilling.filters import (SelectSMSBillableDomainsFilter, SelectSMSDirectionFilter,
                               SelectActivelyBillableDomainsFilter)
from hqbilling.models import HQMonthlyBill, SMS_DIRECTIONS, SMSBillable
from hqbilling.reports import HQBillingReport

class BillingDetailReport(GenericTabularReport, HQBillingReport, DatespanMixin):
    """
        Base class for Billing detail reports
    """
    domain_filter_class = None
    report_template_path = "hqbilling/reports/detail_reports.html"

    @property
    def default_datespan(self):
        start, end = HQMonthlyBill.get_default_start_end()
        datespan = DateSpan(start, end, format="%Y-%m-%d", timezone=self.timezone)
        datespan.is_default = True
        return datespan

    @property
    @memoized
    def domains(self):
        domain = self.request.GET.get(self.domain_filter_class.slug)
        if domain:
            return [Domain.get_by_name(domain)]
        if self.request.GET.get(SelectActivelyBillableDomainsFilter.slug) == 'yes':
            return SelectActivelyBillableDomainsFilter.get_marked_domains()
        return self.domain_filter_class.get_billable_domains()

    def _format_bill_amount(self, amount):
        return self.table_cell(amount, "$ %.2f" % amount)

    def _format_client(self, domain):
        return mark_safe(render_to_string('hqbilling/partials/update_client_button.html', {
            'domain':domain.name,
            'client_name': domain.billable_client,
            "is_active": domain.is_sms_billable,
        }))


class SMSDetailReport(BillingDetailReport):
    name = "Messaging Details"
    slug = "sms_detail"
    fields = ['corehq.apps.reports.fields.DatespanField',
              'hqbilling.filters.SelectActivelyBillableDomainsFilter',
              'hqbilling.filters.SelectSMSBillableDomainsFilter',
              'hqbilling.filters.SelectSMSDirectionFilter']
    exportable = True

    domain_filter_class = SelectSMSBillableDomainsFilter

    description = "See all the SMS messages sent during a time frame, per domain, and per direction."

    @property
    @memoized
    def direction(self):
        return self.request.GET.get(SelectSMSDirectionFilter.slug)

    @property
    def headers(self):
        return DataTablesHeader(
            DataTablesColumn("Date", sort_type=DTSortType.DATE),
            DataTablesColumn("Client"),
            DataTablesColumn("Domain"),
            DataTablesColumn("Direction"),
            DataTablesColumn("Backend API"),
            DataTablesColumn("Billing Status"),
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
        for domain in self.domains:
            if self.direction:
                billables = SMSBillable.by_domain_and_direction(domain.name, self.direction,
                    start=self.datespan.startdate_param_utc, end=self.datespan.enddate_param_utc)
            else:
                billables = SMSBillable.by_domain(domain.name,
                    start=self.datespan.startdate_param_utc, end=self.datespan.enddate_param_utc)

            for billable in billables:
                totals[0] += billable.converted_billable_amount
                totals[1] += billable.dimagi_surcharge
                totals[2] += billable.total_billed
                rows.append([
                    self.table_cell(billable.billable_date.isoformat(),
                        billable.billable_date.strftime("%B %d, %Y %H:%M:%S")),
                    self._format_client(domain),
                    domain.name,
                    SMS_DIRECTIONS.get(billable.direction),
                    billable.api_name(),
                    render_to_string("hqbilling/partials/billing_status_details.html", {
                        'has_error': billable.has_error,
                        'error_msg': billable.error_message,
                        'billable_type': billable.api_name(),
                        'billed_date': billable.billable_date.strftime("%d %b %Y at %H.%M UTC"),
                        'billable_id': billable._id,
                    }),
                    self._format_bill_amount(billable.converted_billable_amount),
                    self._format_bill_amount(billable.dimagi_surcharge),
                    self._format_bill_amount(billable.total_billed)
                ])
        self.total_row = ["", "", "", "", "", "Total Billed:"] + ["%.2f" % t for t in totals]
        return rows


class MonthlyBillReport(BillingDetailReport):
    name = "Monthly Bill by Domain"
    slug = "monthly_bill"
    fields = ['corehq.apps.reports.fields.DatespanField',
              'hqbilling.filters.SelectActivelyBillableDomainsFilter',
              'hqbilling.filters.SelectSMSBillableDomainsFilter']
    report_template_path = "hqbilling/reports/monthly_bill_summary_report.html"

    domain_filter_class = SelectSMSBillableDomainsFilter

    @property
    def headers(self):
        return DataTablesHeader(
            DataTablesColumn("Domain"),
            DataTablesColumn("Client"),
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

        for domain in self.domains:
            all_bills = HQMonthlyBill.get_bills(domain.name,
                start=self.datespan.startdate_param_utc,
                end=self.datespan.enddate_param_utc
            ).all()
            for bill in all_bills:
                nice_start = bill.billing_period_start.strftime("%B %d, %Y")
                nice_end = bill.billing_period_end.strftime("%B %d, %Y")
                rows.append([
                    domain.name,
                    self._format_client(domain),
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
                            'domain': domain.name,
                        }))
                    ),
                    mark_safe('<a href="%s" class="btn btn-primary">View Invoice</a>' %
                        reverse("billing_invoice", kwargs=dict(bill_id=bill.get_id))),
                    mark_safe('<a href="%s" class="btn"><i class="icon icon-list"></i> View Itemized</a>' %
                        reverse("billing_itemized", kwargs=dict(bill_id=bill.get_id)))
                ])

        return rows
