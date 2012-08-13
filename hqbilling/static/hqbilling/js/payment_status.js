var PaymentStatusManager = function(o) {
    var self = this;
    self.modal = o.modal || $('#changePaymentStatusModal');
    self.text = {
        yes: "paid",
        no: "not paid"
    };
    self.button_classes = {
        yes: "btn-success",
        no: "btn-warning"
    };
    self.label_classes = {
        yes: "label-success",
        no: "label-important"
    }
    self.modal.on('show')
};