from django.conf.urls.defaults import *

payments_admin = patterns('hqpayments.views',
    url(r'^delete/all/', "deltestdata"),
    url(r'^forms/(?P<rate_form>[\w_]+)/(?P<rate_item_type>[\w_]+)/(?P<rate_id>[\w_]+)/$', 'billing_rate_form', name='billing_rate_form'),
    url(r'^forms/(?P<rate_form>[\w_]+)/$', 'billing_rate_form', name='billing_rate_form'),
    url(r'^async/filters/(?P<report_slug>[\w_]+)/$', 'billing_report_dispatcher', name="billing_report_async_filter_dispatcher", kwargs={
        'async_filters': True
    }),
    url(r'^async/(?P<report_slug>[\w_]+)/$', 'billing_report_dispatcher', name="billing_report_async_dispatcher", kwargs={
        'async': True
    }),
    url(r'^(?P<report_slug>[\w_]+)/$', 'billing_report_dispatcher', name="billing_report_dispatcher"),
)