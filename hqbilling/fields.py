from corehq.apps.reports.fields import DatespanField, ReportSelectField
from dimagi.utils.couch.database import get_db
from hqbilling.models import OUTGOING, SMS_DIRECTIONS, INCOMING

class SelectSMSBillableDomainsField(ReportSelectField):
    slug = "b_domain"
    name = "Select Project"
    cssId = "billable_domain_select"
    cssClasses = "span6"
    default_option = "Choose a project..."
    as_combo = True
    billable_view = 'hqbilling/all_billable_items'

    def update_params(self):
        domains = self.get_billable_domains()
        self.selected = self.request.GET.get(self.slug,'')
        self.options = [dict(val=d, text=d) for d in domains]

    @classmethod
    def get_billable_domains(cls):
        key = ["billable"]
        data = get_db().view(cls.billable_view,
            group=True,
            startkey=key,
            endkey=key+[{}]
        ).all()
        return [item.get("key",[])[1] for item in data]

class SelectSMSDirectionField(ReportSelectField):
    slug = "direction"
    name = "Select Direction"
    cssId = "sms_direction_select"
    default_option = "Any Direction"
    cssClasses = "span2"
    options = [dict(val=OUTGOING, text=SMS_DIRECTIONS.get(OUTGOING)), dict(val=INCOMING, text=SMS_DIRECTIONS.get(INCOMING))]

class SelectPaymentStatusField(ReportSelectField):
    slug = "paid"
    name = "Payment Status"
    cssId = "payment_status_select"
    default_option = "Any Status"
    cssClasses = "span2"
    options = [dict(val="no", text="Not Paid"), dict(val="yes", text="Paid")]

class SelectBilledDomainsField(SelectSMSBillableDomainsField):
    billable_view = 'hqbilling/monthly_bills'

class DatespanBillingStartField(DatespanField):
    name = "Range for Start of Billing Period"