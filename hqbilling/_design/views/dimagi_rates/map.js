function (doc) {
    if (doc.doc_type === 'DimagiDomainSMSRate') {
        emit([doc.direction, doc.domain, doc._id], 1);
    }
}