function (doc) {
    if (doc.doc_type === 'TaxRateByCountry' ) {
        emit([doc.country.toLowerCase(), doc._id], 1);
    }
}