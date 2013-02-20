import datetime
import calendar
from django.core.management.base import LabelCommand, CommandError
import sys
from corehq.apps.domain.models import Domain
from corehq.apps.sms.models import MessageLog
from dimagi.utils.modules import to_function
from hqbilling.fields import SelectSMSBillableDomainsField
from hqbilling.management.commands import month_span
from hqbilling.models import SMSBillable, SMSRate

class Command(LabelCommand):
    help = "Recalculate sms rates for a particular month."
    args = "<year, ex: 2012> <month integer: 1-12> <optional: domain>"
    label = ""

    def handle(self, *args, **options):
        if len(args) < 2:
            raise CommandError("year and month are required")

        if len(args) > 2:
            domains = [args[2]]
        else:
            domains = SelectSMSBillableDomainsField.get_billable_domains()

        first_day, last_day = month_span(int(args[0]), int(args[1]))
        print "\nRecalculating SMS Billables\n----\n"
        for domain in domains:
            billables_for_domain = SMSBillable.by_domain(domain,
                start=first_day.isoformat(), end=last_day.isoformat()).all()
            print "Found %d SMS Billables for domain %s" % (len(billables_for_domain), domain)
            for billable in billables_for_domain:
                rate_doc = SMSRate.get_db().get(billable.rate_id)
                rate_class = to_function("hqbilling.models.%s" % rate_doc.get('doc_type', 'SMSRate'))
                rate_item = rate_class.get(rate_doc['_id'])
                billable.calculate_rate(rate_item, real_time=False)
                billable.save()
                sys.stdout.write(".")
                sys.stdout.flush()
            print "\n"
