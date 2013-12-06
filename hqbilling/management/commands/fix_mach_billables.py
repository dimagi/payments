from django.core.management.base import NoArgsCommand
from corehq.apps.sms.models import MessageLog
from dimagi.utils.couch.database import iter_docs
from hqbilling.models import MachSMSBillable


class Command(NoArgsCommand):
    help = "Fixes MACH Billable billable_date from Aug 1st to Nov 30, 2011"

    def handle_noargs(self, *args, **options):
        mach_billables = MachSMSBillable.get_db().view(
            "hqbilling/sms_billables",
            startkey=["billable type date", "MachSMSBillable", "2013-08-01"],
            endkey=["billable type date", "MachSMSBillable", "2013-11-30"],
            reduce=False,
        ).all()
        mach_billables_ids = [billable['id'] for billable in mach_billables]
        billable_num = 0
        total_billables = len(mach_billables_ids)
        for billable_doc in iter_docs(MachSMSBillable.get_db(), mach_billables_ids):
            billable_num += 1
            billable = MachSMSBillable.wrap(billable_doc)
            message_log = MessageLog.get(billable.log_id)
            billable.billable_date = message_log.date
            billable.save()
            print "(%d/%d) Successfully restored billable date on Mach Billable %s to %s" \
                  % (billable_num, total_billables, billable._id, billable.billable_date)
