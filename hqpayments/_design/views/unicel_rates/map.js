function (doc) {
    if (doc.doc_type === 'UnicelSMSBillableRate') {
        emit([doc.direction, doc._id], 1);
    }
}