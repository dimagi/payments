function (doc) {
    if (["MachSMSRate", "DimagiDomainSMSRate", "TropoSMSRate", "UnicelSMSRate"].indexOf(doc.doc_type) >= 0) {
        emit(["all", doc.doc_type, doc.direction], 1);

        if (doc.doc_type === 'MachSMSRate') {
            emit(["type", doc.doc_type, doc.direction, doc.country, doc.network, doc._id], 1);
        }
        if (doc.doc_type === 'DimagiDomainSMSRate') {
            emit(["type", doc.doc_type, doc.direction, doc.domain, doc._id], 1);
        }
        if (doc.doc_type === 'TropoSMSRate') {
            emit(["type", doc.doc_type, doc.direction, doc.country_code, doc._id], 1);
        }
        if (doc.doc_type === 'UnicelSMSRate') {
            emit(["type", doc.doc_type, doc.direction, doc._id], 1);
        }
    }
}
