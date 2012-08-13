function (doc) {
    if (doc.doc_type === 'TropoSMSBillable') {
        emit(["domain", doc.domain, doc.billable_date], 1);
        emit(["direction", doc.domain, doc.direction, doc.billable_date], 1);
    }
}