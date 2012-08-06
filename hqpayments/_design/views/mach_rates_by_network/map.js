function (doc) {
    if (doc.doc_type === 'MachSMSBillableRate') {
        emit([doc.direction, doc.country, doc.network, doc._id], 1);
    }
}