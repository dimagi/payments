from dimagi.utils.modules import to_function
import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponse, HttpResponseNotFound, Http404
import json
from django.template.loader import render_to_string
from corehq.apps.domain.decorators import login_and_domain_required, require_superuser
from corehq.apps.reports.views import report_dispatcher
from dimagi.utils.web import render_to_response
from hqpayments.forms import *
from hqpayments.models import *

@require_superuser
def billing_report_dispatcher(request, report_slug, return_json=False, report_map='BILLING_REPORT_MAP', export=False, custom=False, async=False, async_filters=False, static_only=False):
    mapping = getattr(settings, report_map, None)
    if not mapping:
        return HttpResponseNotFound("Sorry, no reports have been configured yet.")
    for key, models in mapping.items():
        for model in models:
            klass = to_function(model)
            if klass.slug == report_slug:
                k = klass(None, request)
                if return_json:
                    return k.as_json()
                elif export:
                    return k.as_export()
                elif async:
                    return k.as_async(static_only=static_only)
                elif async_filters:
                    return k.as_async_filters()
                else:
                    return k.as_view()
    raise Http404

@require_superuser
def billing_rate_form(request, rate_form, rate_item_type="", rate_id="", template="hqpayments/billing/forms/new_rate_default.html"):
    rate_form = eval(rate_form)
    new_rate_form = rate_form()
    success = False
    delete_rate  = request.GET.get('delete')
    did_delete = False
    rate_result = []

    if rate_id and rate_item_type:
        rate_item_type = eval(rate_item_type)
        rate_item = rate_item_type.get(rate_id)
        if delete_rate:
            rate_item.delete()
            success = True
            did_delete = True
        elif request.method == 'POST':
            new_rate_form = rate_form(request.POST)
            if new_rate_form.is_valid():
                success = True
                rate_result = new_rate_form.update(rate_item)
        else:
            new_rate_form = rate_form(rate_item._doc)
    elif request.method == 'POST':
        new_rate_form = rate_form(request.POST)
        if new_rate_form.is_valid():
            rate_result = new_rate_form.save()
            new_rate_form = rate_form()
            success = True

    context = dict(new_rate_form=new_rate_form)
    return HttpResponse(json.dumps(dict(
            success=success,
            deleted=did_delete,
            form_update=render_to_string(template, context),
            rows=rate_result
        )))

def deltestdata(request):
    all_rates = MachSMSBillableRate.view(MachSMSBillableRate.match_view(),
        reduce=False,
        include_docs=True
    ).all()
    for rate in all_rates:
        rate.delete()
    return HttpResponse("done")