function (doc) {
    if (doc.doc_type === 'MachSMSBillable') {
        emit([doc.mach_id, doc._id], 1);
    }
}