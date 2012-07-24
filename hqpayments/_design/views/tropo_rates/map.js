function (doc) {
    if (doc.doc_type === 'TropoSMSBillableRate') {
        emit([doc.direction, doc.domain, doc._id], 1);
    }
}