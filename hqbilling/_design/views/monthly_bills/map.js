function (doc) {
    if (doc.doc_type === 'HQMonthlyBill' ) {
        var is_paid = (doc.paid) ? "yes" : "no";
        emit(["generated", doc.domain, doc.date_generated], 1);
        emit(["generated paid", doc.domain, is_paid, doc.date_generated], 1);
        emit(["start", doc.domain, doc.billing_period_start], 1);
        emit(["start paid", doc.domain, is_paid, doc.billing_period_start], 1);
        emit(["end", doc.domain, doc.billing_period_end], 1);
        emit(["end paid", doc.domain, is_paid, doc.billing_period_end], 1);
        emit(["billable", doc.domain], 1);
    }
}