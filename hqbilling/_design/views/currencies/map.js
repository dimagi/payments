function (doc) {
    if (doc.doc_type === 'BillableCurrency') {
        emit([doc.currency_code, doc._id], 1);
    }
}