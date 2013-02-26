function (doc) {
    if (doc.doc_type === 'Domain') {
        if (doc.is_sms_billable === true) {
            emit(doc.name, 1);
        }
    }
}
