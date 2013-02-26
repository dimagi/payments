function (doc) {
    if (doc.doc_type === 'Domain') {
        if (doc.is_sms_billable === true) {
            emit(["marked", doc.name], 1);
        }
    }
    if (doc.doc_type === 'SMSBillable' ||
        doc.doc_type === 'UnicelSMSBillable' ||
        doc.doc_type === 'TropoSMSBillable' ||
        doc.doc_type === 'MachSMSBillable') {
        var date_billed = new Date(doc.billable_date);
        emit(["received", date_billed.getUTCFullYear(), date_billed.getUTCMonth()+1, doc.domain], 1);
    }
}
