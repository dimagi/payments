function (doc) {
    if (doc.doc_type === 'SMSBillable' ||
        doc.doc_type === 'UnicelSMSBillable' ||
        doc.doc_type === 'TropoSMSBillable' ||
        doc.doc_type === 'MachSMSBillable') {
        var date_billed = new Date(doc.billable_date);
        emit([date_billed.getUTCFullYear(), date_billed.getUTCMonth()+1, doc.domain], 1);
    }
}
