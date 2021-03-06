from collections import defaultdict
from django.utils.translation import ugettext_noop
import operator
from corehq.apps.domain.models import Domain
from corehq.apps.reports.filters.base import BaseSingleOptionTypeaheadFilter, BaseSingleOptionFilter
from hqbilling.models import SMS_DIRECTIONS, SMSBillable, HQMonthlyBill


class SelectSMSBillableDomainsFilter(BaseSingleOptionTypeaheadFilter):
    slug = "b_domain"
    label = "Select Domain"
    default_text = ugettext_noop("Select Domain...")

    @classmethod
    def get_billable_domains(cls):
        marked_domains = SMSBillable.get_db().view('hqbilling/domains_marked_for_billing', reduce=False).all()

        prev_month, _ = HQMonthlyBill.get_default_start_end()

        recent = SMSBillable.get_db().view('hqbilling/domains_with_billables',
                                           startkey=[prev_month.year, prev_month.month],
                                           group=True,
                                           group_level=3).all()
        
        recent_counts = defaultdict(int)
        for r in recent:
            recent_counts[r['key'][-1]] += r['value']
        for m in marked_domains:
            if m['key'] not in recent_counts.keys():
                recent_counts[m['key']] = 0

        all_time = SMSBillable.get_db().view('hqbilling/domains_with_billables',
                                             group=True,
                                             group_level=3).all()
        all_time_counts = defaultdict(int)
        for a in all_time:
            if a['key'][-1] not in recent_counts.keys():
                all_time_counts[a['key'][-1]] += a['value']

        sorted_recent = sorted(recent_counts.iteritems(), key=operator.itemgetter(1), reverse=True)
        sorted_all_time = sorted(all_time_counts.iteritems(), key=operator.itemgetter(1), reverse=True)

        return [Domain.get_by_name(r[0]) for r in sorted_recent if r[0]] + \
               [Domain.get_by_name(a[0]) for a in sorted_all_time if a[0]]

    @property
    def options(self):
        if self.request.GET.get(SelectActivelyBillableDomainsFilter.slug) == 'yes':
            domain_list = SelectActivelyBillableDomainsFilter.get_marked_domains()
        else:
            domain_list = self.get_billable_domains()
        return [(domain.name, "%s [%s]" % (domain.name, domain.billable_client or "No FB Client"))
                for domain in domain_list]

class SelectSMSDirectionFilter(BaseSingleOptionFilter):
    slug = "direction"
    label = "Select Direction"
    default_text = ugettext_noop("Any Direction")

    @property
    def options(self):
        return SMS_DIRECTIONS.items()

class SelectActivelyBillableDomainsFilter(BaseSingleOptionFilter):
    slug = "is_active_bill"
    label = "Domain's Billable Status"
    default_text = "Any Billable Status"

    @classmethod
    def get_marked_domains(cls, as_names=False):
        marked_domains = SMSBillable.get_db().view('hqbilling/domains_marked_for_billing', reduce=False).all()
        marked_domains = [m['key'] for m in marked_domains]
        return marked_domains if as_names else [Domain.get_by_name(d) for d in marked_domains]

    @property
    def options(self):
        return [('yes', 'Show Actively Billable Only')]


class SelectBillableDuplicateFilter(BaseSingleOptionFilter):
    slug = "dupes"
    label = "Handle Duplicates"
    default_text = "Show Most Recent"
    options = [
        ('all', "Show All")
    ]
