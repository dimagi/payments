function (doc) {
    if (doc.doc_type === 'MachSMSBillableItem') {
        if (!doc.mach_delivered_date)
            emit([doc._id, doc.mach_contacted_api], 1);
    }
}