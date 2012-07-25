function (doc) {
    if (doc.doc_type === 'MachSMSBillableRate') {
        var mnc_list = doc.mnc.split(" ");
        for (var m in mnc_list)
            emit([doc.direction, doc.country_code, doc.mcc, mnc_list[m], doc._id], 1);
    }
}