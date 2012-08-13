function (doc) {
    if (doc.doc_type === 'UnicelSMSRate') {
        emit([doc.direction, doc._id], 1);
    }
}