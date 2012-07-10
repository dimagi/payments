function (doc) {
    if (doc.doc_type === 'MachSMSBillableRate') {
        emit([doc.direction, doc.country_code, doc.mcc, doc.mnc, doc._id], 1);
    }
}