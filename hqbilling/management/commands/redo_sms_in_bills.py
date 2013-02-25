from django.core.management.base import LabelCommand, CommandError
import sys
from hqbilling.filters import SelectSMSBillableDomainsFilter
from hqbilling.management.commands import month_span
from hqbilling.models import OUTGOING, INCOMING, HQMonthlyBill

class Command(LabelCommand):
    help = "Recalculate sms billed for bills generated in a particular month."
    args = "<year, ex: 2012> <month integer: 1-12> <optional: domain>"
    label = ""

    def handle(self, *args, **options):
        if len(args) < 2:
            raise CommandError("year and month are required")

        if len(args) > 2:
            domains = [Domain.get_by_name(args[2])]
        else:
            domains = SelectSMSBillableDomainsFilter.get_billable_domains()

        first_day, last_day = month_span(int(args[0]), int(args[1]))
        print "\nRecalculating SMS in HQ Bills\n----\n"
        for domain in domains:
            bills_for_domain = HQMonthlyBill.get_bills(domain.name,
                start=first_day.isoformat(),
                end=last_day.isoformat()).all()
            print "Found %d SMS Bills for domain %s" % (len(bills_for_domain), domain.name)
            for bill in bills_for_domain:
                bill._get_sms_activities(INCOMING)
                bill._get_sms_activities(OUTGOING)
                bill.save()
                sys.stdout.flush()
            print "\n"
