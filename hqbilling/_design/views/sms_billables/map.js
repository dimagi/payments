function (doc) {
    if (doc.doc_type === 'SMSBillable' ||
        doc.doc_type === 'UnicelSMSBillable' ||
        doc.doc_type === 'TropoSMSBillable' ||
        doc.doc_type === 'MachSMSBillable' ) {

        emit(["domain", doc.domain, doc.billable_date], 1);
        emit(["type domain", doc.doc_type, doc.domain, doc.billable_date], 1);
        emit(["domain log_id", doc.domain, doc.log_id, doc.billable_date], 1);

        emit(["domain direction", doc.domain, doc.direction, doc.billable_date], 1);
        emit(["type domain direction", doc.doc_type, doc.domain, doc.direction, doc.billable_date], 1);

        emit(["billable", doc.domain], 1);
        emit(["billable date", doc.billable_date, doc.domain], 1);
    }
}
