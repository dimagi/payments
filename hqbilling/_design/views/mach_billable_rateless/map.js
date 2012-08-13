function (doc) {
    if (doc.doc_type === 'MachSMSBillable') {
        if (!doc.rate_id)
            emit([doc._id, doc.mach_contacted_api], 1);
    }
}