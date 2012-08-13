function (doc) {
    if (doc.doc_type === 'TropoSMSRate') {
        emit([doc.direction, doc.country_code, doc._id], 1);
    }
}