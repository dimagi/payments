import datetime
from django.test import TestCase
from corehq.apps.domain.models import Domain
from hqbilling.models import (SMSBillable, INCOMING, OUTGOING, HQMonthlyBill, MachSMSBillable,
                              UnicelSMSBillable, TropoSMSBillable)
from hqbilling.tasks import generate_monthly_bills

class TestMonthlyBillFewUsers(TestCase):

    def setUp(self):
        two_weeks_ago = datetime.datetime.utcnow()-datetime.timedelta(days=14)

        for domain in Domain.get_all():
            domain.delete()

        all_billables = SMSBillable.get_all()
        # all_billables contains duplicates; only delete each doc once
        for b_id in set(b._id for b in all_billables):
            SMSBillable.get_db().delete_doc(b_id)

        self.domain = Domain()
        self.domain.name = "domain_with_sms"
        self.domain.is_active = True
        self.domain.date_created = two_weeks_ago
        self.domain.save()

        # Incoming billables

        self.tropo_bill = TropoSMSBillable()
        self.tropo_bill.billable_date = two_weeks_ago
        self.tropo_bill.billable_amount = 2
        self.tropo_bill.conversion_rate = 1
        self.tropo_bill.dimagi_surcharge = 0.002
        self.tropo_bill.rate_id = "INCOMING_RATE_TROPO"
        self.tropo_bill.log_id = "INCOMING_LOG_TROPO"
        self.tropo_bill.domain = self.domain.name
        self.tropo_bill.direction = INCOMING
        self.tropo_bill.phone_number = "+15551234567"
        self.tropo_bill.tropo_id = "TROPO_ID"
        self.tropo_bill.save()

        # Outgoing billables

        self.mach_bill = MachSMSBillable()
        self.mach_bill.billable_date = two_weeks_ago
        self.mach_bill.contacted_mach_api = two_weeks_ago
        self.mach_bill.mach_delivered_date = two_weeks_ago
        self.mach_bill.billable_amount = 0.01
        self.mach_bill.conversion_rate = 1.2
        self.mach_bill.dimagi_surcharge = 0.002
        self.mach_bill.rate_id = "OUTGOING_MACH_RATE"
        self.mach_bill.log_id = "OUTGOING_MACH_LOG"
        self.mach_bill.domain = self.domain.name
        self.mach_bill.direction = OUTGOING
        self.mach_bill.phone_number = "+15551234567"
        self.mach_bill.mach_delivery_status = "delivered"
        self.mach_bill.mach_id = "MACH_MESSAGE_ID"
        self.mach_bill.save()

        self.unicel_bill = UnicelSMSBillable()
        self.unicel_bill.billable_date = two_weeks_ago
        self.unicel_bill.billable_amount = 2
        self.unicel_bill.conversion_rate = 1
        self.unicel_bill.dimagi_surcharge = 0.002
        self.unicel_bill.rate_id = "OUTGOING_UNICEL_RATE"
        self.unicel_bill.log_id = "OUTGOING_UNICEL_LOG"
        self.unicel_bill.domain = self.domain.name
        self.unicel_bill.direction = OUTGOING
        self.unicel_bill.phone_number = "+15551234567"
        self.unicel_bill.unicel_id = "UNICEL_ID"
        self.unicel_bill.save()


    def tearDown(self):
        self.mach_bill.delete()
        self.unicel_bill.delete()
        self.tropo_bill.delete()

        self.domain.delete()

    def testSMSBilling(self):
        generate_monthly_bills()
        last_bill = HQMonthlyBill.get_bills(self.domain.name).first()
        if last_bill:
            self.assertEqual(self.tropo_bill.total_billed,
                last_bill.incoming_sms_billed)
            self.assertEqual(self.unicel_bill.total_billed+self.mach_bill.total_billed,
                last_bill.outgoing_sms_billed)
        else:
            raise Exception("Monthly Bill not successfully generated.")
