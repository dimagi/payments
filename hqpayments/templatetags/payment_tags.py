from django import template
from django.core.urlresolvers import reverse
from dimagi.utils.modules import to_function
import settings

register = template.Library()

@register.simple_tag
def payment_report_list(current_slug="", report_map="BILLING_REPORT_MAP"):
    mapping = getattr(settings, report_map, None)
    if not mapping: return ""
    lst = []
    for key, models in mapping.iteritems():
        sublist = []
        nav_header = '<li class="nav-header">%s</li>' % key
        for model in models:
            klass = to_function(model)
            sublist.append('<li%s><a href="%s" title="%s">' %\
                           ((' class="active"' if klass.slug == current_slug else ""),
                            reverse('billing_report_dispatcher', kwargs=dict(report_slug=klass.slug)),
                            klass.description))
            sublist.append('%s</a></li>' % klass.name)
        if sublist:
            lst.append(nav_header)
            lst.extend(sublist)
    return "\n".join(lst)