function (doc) {
    if (doc.doc_type === 'HQMonthlyBill' ) {
        emit(["generated", doc.domain, doc.date_generated], 1);
        emit(["start", doc.domain, doc.billing_period_start], 1);
        emit(["end", doc.domain, doc.billing_period_end], 1);
        emit(["billable", doc.domain], 1);
    }
}