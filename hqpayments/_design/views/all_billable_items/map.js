function (doc) {
    if (doc.doc_type === 'SMSBillableItem' ||
        doc.doc_type === 'UnicelSMSBillableItem' ||
        doc.doc_type === 'TropoSMSBillableItem' ||
        doc.doc_type === 'MachSMSBillableItem' ) {

        emit(["domain", doc.domain, doc.billable_date], 1);
        emit(["domain direction", doc.domain, doc.direction, doc.billable_date], 1);
        emit(["billable", doc.domain], 1);
    }
}