from django.utils.translation import ugettext_noop
from corehq.apps.domain.models import Domain
from corehq.apps.reports.filters.base import BaseSingleOptionTypeaheadFilter
from dimagi.utils.decorators.memoized import memoized


class SelectSMSBillableDomainsFilter(BaseSingleOptionTypeaheadFilter):
    slug = "b_domain"
    label = "Select Billable Project"
    default_text = ugettext_noop("Select Project...")

    @classmethod
    def get_billable_domains(cls):
        return Domain.view('hqbilling/sms_billable_domains',
                reduce=False,
                include_docs=True
            ).all()

    @property
    def options(self):
        return [(domain.name, domain.name) for domain in self.get_billable_domains()]
