from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from corehq.apps.domain.decorators import login_and_domain_required
from dimagi.utils.web import render_to_response

@login_and_domain_required
def default(request, template="payments/payments_base.html"):

    return render_to_response(request, template, dict())