function (doc) {
    if (doc.doc_type === 'MachSMSBillableItem') {
        emit([doc.mach_id, doc._id], 1);
    }
}