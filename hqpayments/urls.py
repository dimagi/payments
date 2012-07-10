from django.conf.urls.defaults import *

payments_admin = patterns('hqpayments.views',
    url(r'^$', 'admin_overview', name='payments_admin_default'),
    #    url(r'^sms_backends/(?P<backend>[\w_]+)/$', 'manage_sms_rates', name='payments_manage_backend'),
        url(r'^sms_backends/mach/$', 'mach_backend', name='payments_mach_backend'),
)