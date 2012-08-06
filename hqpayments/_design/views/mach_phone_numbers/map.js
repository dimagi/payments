function (doc) {
    if (doc.doc_type === 'MachPhoneNumber') {
        emit([doc.phone_number, doc._id], 1);
    }
}