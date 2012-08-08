from corehq.apps.reports.custom import HQReport

class HQBillingReport(HQReport):
    base_slug = 'billing'
    reporting_section_name = "HQ Billing"
    base_template_name = "hqpayments/billing/billing_reports_base.html"
    asynchronous = True
    is_admin_report = True
    global_root = "/hq/billing/"