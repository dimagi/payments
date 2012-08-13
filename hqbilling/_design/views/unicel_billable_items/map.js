function (doc) {
    if (doc.doc_type === 'UnicelSMSBillable') {
        emit(["domain", doc.domain, doc.billable_date], 1);
        emit(["domain direction", doc.domain, doc.direction, doc.billable_date], 1);
    }
}