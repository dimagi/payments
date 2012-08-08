from corehq.apps.reports.datatables import DataTablesColumn, DataTablesHeader, DTSortType, DataTablesColumnGroup
from corehq.apps.reports.standard import StandardTabularHQReport, StandardHQReport, StandardDateHQReport
from corehq.apps.reports import util as report_utils
from hqpayments.fields import SelectSMSBillableDomainsField, SelectSMSDirectionField, SelectBilledDomainsField
from hqpayments.reports.billing import HQBillingReport
from hqpayments.models import *

class SMSDetailReport(HQBillingReport, StandardTabularHQReport, StandardDateHQReport):
    name = "Messaging"
    slug = "sms_detail"
    fields = ['corehq.apps.reports.fields.DatespanField',
              'hqpayments.fields.SelectSMSBillableDomainsField',
              'hqpayments.fields.SelectSMSDirectionField']

    def get_parameters(self):
        self.project = self.request.GET.get(SelectSMSBillableDomainsField.slug)
        self.direction = self.request.GET.get(SelectSMSDirectionField.slug)
        self.total_billed = 0

    def get_headers(self):
        return DataTablesHeader(DataTablesColumn("Direction", span=2),
            DataTablesColumn("Project", span=3),
            DataTablesColumn("Backend API", span=2),
            DataTablesColumn("Date", span=2),
            DataTablesColumn("Amount", span=3)
        )

    def get_rows(self):
        rows = []
        if self.direction:
            billables = SMSBillableItem.by_domain_and_direction(self.project, self.direction,
                start=self.datespan.startdate_param_utc, end=self.datespan.enddate_param_utc).all()
        else:
            billables = SMSBillableItem.by_domain(self.project,
                start=self.datespan.startdate_param_utc, end=self.datespan.enddate_param_utc).all()
        for billable in billables:
            converted_total = billable.conversion_rate*billable.billable_amount
            self.total_billed += converted_total
            rows.append([
                SMS_DIRECTIONS.get(billable.direction),
                self.project,
                billable.api_name,
                billable.billable_date,
                "$ %.2f" % converted_total
            ])
        self.total_row = ["","","","Total Billed:", "$ %.2f" % self.total_billed]
        return rows

    def generate_billable_rows(self, billable_class):
        rows = []
        billable_class = eval(billable_class)
        if self.direction:
            billables = billable_class.by_domain_and_direction(self.project, self.direction,
                            start=self.datespan.startdate_param_utc, end=self.datespan.enddate_param_utc).all()
        else:
            billables = billable_class.by_domain(self.project,
                            start=self.datespan.startdate_param_utc, end=self.datespan.enddate_param_utc).all()
        for billable in billables:
            converted_total = billable.conversion_rate*billable.billable_amount
            self.total_billed += converted_total
            rows.append([
                SMS_DIRECTIONS.get(billable.direction),
                self.project,
                billable.api_name,
                billable.billable_date,
                "$ %.2f" % converted_total
            ])
        return rows

class MonthlyBillReport(HQBillingReport, StandardTabularHQReport, StandardDateHQReport):
    name = "Monthly Bill by Project"
    slug = "monthly_bill"
    fields = ['hqpayments.fields.DatespanBillingStartField',
              'hqpayments.fields.SelectBilledDomainsField']

    def get_parameters(self):
        project = self.request.GET.get(SelectBilledDomainsField.slug)
        all_projects = SelectBilledDomainsField.get_billable_domains()
        self.projects = [project] if project else all_projects

    def get_headers(self):
        return DataTablesHeader(DataTablesColumn("Project"),
            DataTablesColumnGroup("Billing Period",
                DataTablesColumn("Start"),
                DataTablesColumn("End"),
            ),
            DataTablesColumnGroup("Messaging Expenses",
                DataTablesColumn("Incoming"),
                DataTablesColumn("Outgoing"),
                DataTablesColumn("All")
            ),
            DataTablesColumnGroup("User Expenses",
                DataTablesColumn("# Active Users"),
                DataTablesColumn("Total Charges")
            ),
            DataTablesColumn("Total Bill"),
            DataTablesColumn("View Bill", sortable=False)
        )

    def get_rows(self):
        rows = []

        print self.projects
        for project in self.projects:
            all_bills = HQMonthlyBill.get_bills(project,
                start=self.datespan.startdate_param_utc,
                end=self.datespan.enddate_param_utc
            ).all()
            for bill in all_bills:
                rows.append([
                    project,
                    bill.billing_period_start,
                    bill.billing_period_end,
                    self.format_bill_amount(bill.all_incoming_sms_billed),
                    self.format_bill_amount(bill.all_outgoing_sms_billed),
                    self.format_bill_amount(bill.all_incoming_sms_billed+bill.all_outgoing_sms_billed),
                    len(bill.active_users),
                    bill.active_users_billed,
                    self.format_bill_amount(bill.all_incoming_sms_billed+bill.all_outgoing_sms_billed+bill.active_users_billed),
                    '<a href="#" class="btn btn-primary">View Detail</a>'
                ])

        return rows

    @staticmethod
    def format_bill_amount(amount):
        return report_utils.format_datatables_data(text="$ %.2f" % amount, sort_key=amount)