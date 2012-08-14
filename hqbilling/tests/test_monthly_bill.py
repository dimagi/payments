import datetime
import logging
import decimal
from django.test import TestCase
from corehq.apps.domain.models import Domain
from corehq.apps.users.models import CommCareUser
from hqbilling.models import SMSBillable, INCOMING, OUTGOING, HQMonthlyBill, ACTIVE_USER_RATE
from hqbilling.tasks import generate_monthly_bills

class TestMonthlyBillFewUsers(TestCase):

    def setUp(self):
        two_weeks = datetime.timedelta(days=15)

        for domain in Domain.get_all():
            domain.delete()

        all_users = CommCareUser.view('users/by_username',
            include_docs=True,
            reduce=False
        ).all()
        for user in all_users:
            user.delete()

        all_billables = SMSBillable.get_all()
        for billable in all_billables:
            billable.delete()

        self.domain = Domain()
        self.domain.name = "ihavefewusers"
        self.domain.is_active = True
        self.domain.date_created = datetime.datetime.utcnow()-two_weeks
        self.domain.save()

        self.bill_in = SMSBillable()
        self.bill_in.billable_date = datetime.datetime.utcnow()-two_weeks
        self.bill_in.billable_amount = 1
        self.bill_in.conversion_rate = 1.2
        self.bill_in.dimagi_surcharge = 0.002
        self.bill_in.rate_id = "INCOMING_RATE"
        self.bill_in.log_id = "INCOMING_LOG"
        self.bill_in.domain = self.domain.name
        self.bill_in.direction = INCOMING
        self.bill_in.phone_number = "+15551234567"
        self.bill_in.save()

        self.bill_out = SMSBillable()
        self.bill_out.billable_date = datetime.datetime.utcnow()-two_weeks
        self.bill_out.billable_amount = 2
        self.bill_out.conversion_rate = 1
        self.bill_in.dimagi_surcharge = 0.002
        self.bill_out.rate_id = "OUTGOING_RATE"
        self.bill_out.log_id = "OUTGOING_LOG"
        self.bill_out.domain = self.domain.name
        self.bill_out.direction = OUTGOING
        self.bill_out.phone_number = "+15551234567"
        self.bill_out.save()

        # generate 20 active users
        self.user_list = []
        self.num_active_users = 20
        for i in range(0,self.num_active_users):
            commcare_user = CommCareUser.create(self.domain.name, "fakeuser%d"%i, "password1")
            commcare_user.is_active = True
            commcare_user.save()


    def tearDown(self):
        self.bill_in.delete()
        self.bill_out.delete()

        for user in self.user_list:
            user.delete()

        self.domain.delete()

    def testFewUsersWithSMS(self):
        logging.info("Testing few users with SMS")
        generate_monthly_bills()
        last_bill = HQMonthlyBill.get_bills(self.domain.name).first()
        if last_bill:
            self.assertEqual(self.bill_in.total_billed,
                last_bill.incoming_sms_billed)
            self.assertEqual(self.bill_out.total_billed,
                last_bill.outgoing_sms_billed)
            self.assertEqual(self.num_active_users, len(last_bill.active_users))
            self.assertEqual(0, last_bill.active_users_billed)
        else:
            raise Exception("Monthly Bill not successfully generated.")


class TestMonthlyBillManyUsers(TestCase):

    def setUp(self):
        all_users = CommCareUser.view('users/by_username',
            include_docs=True,
            reduce=False
        ).all()

        for user in all_users:
            user.delete()

        self.domain = Domain()
        self.domain.name = "ihavemanyusers"
        self.domain.is_active = True
        self.domain.date_created = datetime.datetime.utcnow()
        self.domain.save()

        # generate 21 active users
        self.user_list = []
        self.num_active_users = 21
        for i in range(0,self.num_active_users):
            commcare_user = CommCareUser.create(self.domain.name, "fakeuser%d"%i, "password1")
            commcare_user.is_active = True
            commcare_user.save()

    def tearDown(self):
        for user in self.user_list:
            user.delete()
        self.domain.delete()

    def testManyUsersWithoutSMS(self):
        logging.info("Testing many users withut SMS")
        generate_monthly_bills()
        last_bill = HQMonthlyBill.get_bills(self.domain.name).first()
        if last_bill:
            self.assertEqual(0,
                last_bill.incoming_sms_billed)
            self.assertEqual(0,
                last_bill.outgoing_sms_billed)
            self.assertEqual(self.num_active_users, len(last_bill.active_users))
            self.assertEqual(decimal.Decimal(self.num_active_users*ACTIVE_USER_RATE), last_bill.active_users_billed)
        else:
            raise Exception("Monthly Bill not successfully generated.")