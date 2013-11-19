function (doc) {
    if (doc.doc_type === 'MachSMSBillable') {
        if (!doc.rate_id) {
            emit(["rateless", doc._id, doc.mach_contacted_api], 1);
        }
        emit(["by mach_id", doc.mach_id, doc._id], 1);
    }
}
